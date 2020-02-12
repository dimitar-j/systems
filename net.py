# Requires Python 3.8

# Imports
import socket
import threading
import json
import random
import time
from typing import Union, List

# Constants
NETWORK_TIMEOUT = 0.1

""" The standard exception type to be thrown by instances of PiNet at runtime.
"""
class PiNetError(Exception):
	pass


""" The standard exception type to be thrown by instances of ArduinoNet at
	runtime.
"""
class ArduinoNetError(Exception):
	pass


""" Encapsulates data to facilitate ownership by local software and usage for
	data requests by peers in the PiNet and ArduinoNet classes.

As Python python does not have C/C++ style pointers, it is necessary to pass
	variables by reference in order for the caller of this module to maintain
	ownership of them. The NetData class is to be instantiated by the caller and
	provided to instances of PiNet or ArduinoNet with the RegisterNetDataObj()
	methods.
"""
class NetData:
	""" Constructs and instance of the NetData class.

	name - A string representing the data housed by the object. Peers will
		refer to specific variables by this name.
	value - The object to be held by this instance. value should only be a basic
		data type available in Python.
	"""
	def __init__(self, name: str, value: any) -> None:
		self.name = name
		self.value = value

""" PiNet is an asynchronous socket wrapper to facilitate communications between
	different Raspberry Pi computers (and indeed other computers). The class is
	intended to facilitate easy communication over LAN using JSON encoding.
	Furthermore, all networking operations are designed to run in separate threads
	to that of the dispatching main program, preventing lockups and allowing time
	critical execution to continue unaffected.
"""
class PiNet:
	""" Constructs a new instance of PiNet.

	isServer - A boolean value indicating if the new PiNet object is to be a
		server (True) or a client (False).
	address - The network address to bind the connection to.
	port - The network port the PiNet will create connections with. Must be
		between 0 and 65535 inclusive.

	Raises PiNetError "Invalid port." when the provided port is not within the
		range 0 to 65535 inclusive.
	"""
	def __init__(self, isServer: bool, address: (str, int)) -> None:
		socket.setdefaulttimeout(NETWORK_TIMEOUT)
		if not 0 <= port <= 65535:
			raise PiNetError("Invalid port.")
		self.__address = address
		self.__isServer = isServer
		self.__responses = {}
		self.__dataObjs = []
		self.__conn = {"thread": None, "conn": None, "host": None,
			"isRunning": False}

	""" Registers a NetData object with the PiNet instance so it may be used to
		service requests from peers.

	obj - The NetData object to be registered.
	"""
	def registerNetDataObj(self, obj: NetData) -> None:
		if not self.__conn["isRunning"]:
			self.__dataObjs.append(obj)
		else:
			raise PiNetError("Cannot register data objects once the connection " \
				"is active.")

	""" Starts the process by which the PiNet instance will seek a network
		connection with other computers. Note that registerNetDataObj may not be
		called once the connection is running.

	Raises PiNetError 'Already running.' if start() has already been called for
		the present instance.
	"""
	def start(self) -> None:
		if self.__conn["thread"] == None:
			if self.__isServer:
				self.__clients = {}
				self.__conn["isRunning"] = True
				self.__conn["thread"] = threading.Thread(target=self.__accpetClients)
				self.__conn["conn"] = socket.socket()
				self.__conn["conn"].bind(self.__address)
				self.__conn["thread"].start()
				self.__conn["conn"].listen()
			else:
				self.__conn["isRunning"] = True
				self.__conn["thread"] = threading.Thread(target=self.__tendServer)
				self.__conn["conn"] = socket.socket()
				self.__conn["conn"].connect(self.__address)
				self.__conn["thread"].start()
		else:
			raise PiNetError("Already running.")		

	""" Called asynchronously in server instances to constantly listen for remote
	clients attempting to connect.
	"""
	def __accpetClients(self) -> None:
		while self.__conn["isRunning"]:
			conn = None
			host = None
			try:
				conn, host = self.__conn["conn"].accept()
				self.__clients[str(host[1])] = {"thread": None, "conn": conn,
					"isRunning": True, "host": host}
				thread = threading.Thread(target=self.__tendClient, 
					args=[self.__clients[str(host[1])]])
				self.__clients[str(host[1])]["thread"] = thread
				thread.start()
			except:
				pass

	""" Called by an asynchronous thread servicing a connection to receive
		messaged from its peer and address them accordingly.

	peer - The connection-specification dictionary for the client to be
		serviced.
	"""
	def __handleRequest(self, peer: dict) -> None:
		request = self.__recvMsg(peer)
		if request == "":
			return
		elif request == "closing":
			if self.__isServer:
				peer["isRunning"] = False
				peer["conn"].close()
				self.__clients.pop(str(peer["host"][1]))
			else:
				self.__conn["isRunning"] = False
			return
		elif "responseKey" in request:
			self.__responses[request["responseKey"]] = request
		else:
			response = {}
			if "query" in request and request["query"][0] == "total_data":
				response = self.__makeTotalNetDataPayload()
			elif "query" in request:
				for i in self.__dataObjs:
					if i.name in request["query"]:
						response[i.name] = i.value
			response["responseKey"] = request["requestKey"]
			if len(response) > 0:
				payload = json.dumps(response, separators=(',', ':'))
				st = threading.Thread(target=self.__sendMsg, args=(peer, payload))
				st.start()

	""" Called asynchronously in server instances to service a connection opened
		with a client.

	peer - The connection-specification dictionary for the client to be
		serviced.
	"""
	def __tendClient(self, peer: dict) -> None:
		while peer["isRunning"]:
			self.__handleRequest(peer)

	""" Called asynchronously in client instances to service a connection opened
		with a server.

	peer - The connection-specification dictionary for the client to be
		serviced.	
	"""
	def __tendServer(self) -> None:
		while self.__conn["isRunning"]:
			self.__handleRequest(self.__conn)

	""" Called by an asynchronous thread to receive messages from a specified
		peer.

	peer - The connection-specification dictionary of the peer the
		message should be received from.
	"""
	def __recvMsg(self, peer: dict) -> dict:
		request = ""
		while True:
			data = None
			try:
				data = peer["conn"].recv(1024)
			except:
				pass
			if data == None:
				if len(request) > 0:
					return json.loads(request)
				else:
					return ""
			else:
				request = request + data.decode()

	""" Called asynchronously to send messages to a specified peer.

	peer - The connection-specification dictionary of the peer the message should
		be sent to.
	payload - A string containing the message to be sent.
	"""
	def __sendMsg(self, peer, payload: str) -> None:
		try:
			peer["conn"].sendall(payload.encode())
		except:
			peer["isRunning"] = False
			peer["conn"].close()
			peer["thread"].join()
			if self.__isServer:
				for host, client in self.__clients.items():
					if client == peer:
						self.__clients.pop(host)
						break
			else:
				self.__conn["thread"] = None

	""" Creates a JSON string of all NetData objects registered with the PiNet
		instance to satisfy a 'total_data' request made by a peer.
	"""
	def __makeTotalNetDataPayload(self) -> str:
		total_data = {}
		for var in self.__dataObjs:
			total_data[var.name] = var.value
		payload = {"total_data": total_data}
		return payload

	""" Makes a 'data_request' to a peer (who must be specified if called
		by a server instance). Returns an responseKey integer to retrieve the
		JSON returned by the peer with getResponse().

	names - A list of NetData names to be requested of the peer. If only
		'total_data', a response containing all of the NetData values maintained by
		the peer will be sent as obtained from ____makeTotalNetDataPayload().
	target - If the caller is a server, it is necessary to specify which client
		the outgoing request is to be sent to. An exception will be raised if target
		is its default value in this case.

	Raises PiNetError 'Target not specified for the request' when the target
		parameter is not given when called by a server instance of PiNet.
	Raises PiNetError 'Target not specified for the request.' when the peer
		targeted by the operation is not connected.
	"""
	def poseQuery(self, names: List[int], target="") -> int:
		requestKey = self.__registerResponse()
		query = {"requestKey": requestKey, "query": names}
		requestPayload = json.dumps(query, separators=(',', ':'))
		if self.__isServer:
			target = str(target)
			if target != "":
				if target in self.__clients and self.__clients[target]["isRunning"]:
					st = threading.Thread(target=self.__sendMsg, 
						args=(self.__clients[target], requestPayload))
					st.start()
				else:
					raise PiNetError("Specified target is not available.")
			else:
				raise PiNetError("Target not specified for the request.")
		else:
			st = threading.Thread(target=self.__sendMsg, 
				args=(self.__conn, requestPayload))
			st.start()
		return requestKey

	""" Called by a method dispatching a request to obtain a responseKey so that
		any data returned in a response may be obtained after with getResponse().

	Raises PiNetError "Fatal, maximum number of pending responses exceeded." when
		there are 256 responses already registered and waiting collection.
		Intentionally left uncaught as under correct implementation and normal
		operation should never occur.
	"""
	def __registerResponse(self) -> int:
		if len(self.__responses) == 256:
			raise PiNetError("Fatal, maximum number of pending responses exceeded.")
		key = random.randint(0, 255)
		while key in self.__responses:
			key = random.randint(0, 255)
		self.__responses[key] = ""
		return key

	""" Called by a thread after dispatching a request to a peer to obtain
		the returned JSON response. 

	key - The responseKey integer returned by the request dispatching function.
	"""
	def getResponse(self, key: int) -> Union[dict, None]:
		if key in self.__responses:
			return self.__responses.pop(key)
		else:
			return None
		
	""" Returns a dictionary containing all pending responseKey response value
		pairs, flushing the internal storage.
	"""
	def getResponses(self) -> dict:
		r = self.__responses
		self.__responses = {}
		return r

	""" Correctly terminates a connection with peers as soon as possible
		and kills all open threads.
	"""
	def stop(self) -> None:
		closePayload = json.dumps("closing", separators=(',', ':')).encode()
		self.__conn["isRunning"] = False
		self.__conn["thread"].join()
		if self.__isServer:
			for host, client in self.__clients.items():
				client["isRunning"] = False
				client["thread"].join()
				try:
					client["conn"].sendall(closePayload)
				except:
					pass
				finally:
					time.sleep(NETWORK_TIMEOUT)
				client["conn"].close()
		else:
			try:
				self.__conn["conn"].sendall(closePayload)
			except:
				pass
			finally:
				time.sleep(NETWORK_TIMEOUT)
		self.__conn["conn"].close()
		return

	""" Returns a list of all the connected client's host names. The names are
		used to target peers when performing operations as a server instance.
		Peers reflected in this list are available to data transmission or
		reception.

	Raises PiNetError "Invalid operation for clients." when called from a client
		instance.
	"""
	def getConnected(self) -> List[str]:
		if self.__isServer:
			return list(self.__clients.keys())
		else:
			raise PiNetError("Invalid operation for clients.")


""" TODO, a similar implementation of PiNet for Arduino computers over USB
"""
class ArduinoNet(PiNet):
	def __init__(self) -> None:
		pass

	def __del__(self) -> None:
		pass

