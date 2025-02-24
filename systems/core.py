from __future__ import annotations

from itertools import count

import zmq
from zmq.utils import jsonapi

from .controllers import controllers


class CoreServer:

    def __init__(self, backend_binding: str, frontend_binding: str):
        """ZMQ server for communication between frontend clients and backend workers.

        Args:
            backend_binding (str): Address of backend binding
            frontend_binding (str): Address of frontend binding
        """
        context = zmq.Context.instance()

        self.backend_binding = backend_binding
        self.frontend_binding = frontend_binding
        self.worker_ids = set()
        self.client_identities = set()

        self.backend = context.socket(zmq.DEALER)
        self.frontend = context.socket(zmq.ROUTER)
        self.poller = zmq.Poller()

        self.is_running = False

    def run(self):
        """Main loop to `run` the server, primarily called through __call__."""
        self.start_listening()
        print("Server listening.")

        while not self.is_fully_connected:
            try:
                self.gather_connections()
            except KeyboardInterrupt:
                return

        self.send_ready_messages()
        print(f"{len(self.worker_ids)} worker(s) ready")
        print(f"Server initialized, connected to {self.client_identities}")

        while self.is_running:
            try:
                self.proxy_messages()
            except KeyboardInterrupt:
                break

        self.frontend.close()
        self.backend.close()
        self.is_running = False

    def start_listening(self):
        """Configure frontend-backend poller and start listening."""
        self.frontend.bind(self.frontend_binding)
        self.backend.bind(self.backend_binding)
        self.poller.register(self.backend, zmq.POLLIN)
        self.poller.register(self.frontend, zmq.POLLIN)

        self.is_running = True

    @property
    def is_fully_connected(self) -> bool:
        """Check if all required clients and workers are connected.

        Returns:
            bool
        """
        # it might be good to parametrize this later on.
        return len(self.client_identities) >= 2 and len(self.worker_ids) >= 1

    def proxy_messages(self):
        """Proxy messages between frontend and backend.

        Currently sending all messages from frontend to backend, all
        messages from backend to frontend. In the future, this is probably
        where the logic for returning message to sender will go.
        """
        incoming_messages = dict(self.poller.poll())

        if self.frontend in incoming_messages:
            message = self.frontend.recv_multipart()
            self.backend.send_multipart(message, zmq.NOBLOCK)

        if self.backend in incoming_messages:
            message = self.backend.recv_multipart()
            self.frontend.send_multipart(message)

    def gather_connections(self):
        """Synchronize start between server and connected sockets."""
        new_connections = dict(self.poller.poll())

        if self.frontend in new_connections:
            [client_identity, _] = self.frontend.recv_multipart()
            self.client_identities.add(client_identity)
            print(f"{client_identity} connected")

        if self.backend in new_connections:
            worker_id = self.backend.recv()
            self.worker_ids.add(worker_id)
            print(f"Worker @ {worker_id} connected")

    def send_ready_messages(self, ready_message: str = b''):
        """Alert frontend and backend connections server is ready to receive.

        Args:
            ready_message (str, optional): Defaults to b''.
        """
        self.backend.send(ready_message)
        for client in self.client_identities:
            self.frontend.send_multipart([client, ready_message])

    def __call__(self) -> None:
        """Treat CoreServer instance as a function.

        ::

            server = CoreServer()
            server() # == server.run()
            Thread(target=server) # == Thread(target=server.run)
        ::
        """
        return self.run()


class ControllerWorker:
    _instance_count = count(0)

    def __init__(self, core_backend_address: str):
        """Controller worker class to process messages and manipulate controllers.

        Args:
            core_backend_address (str): Core backend binding address.
        """
        context = zmq.Context.instance()
        self._id = next(self._instance_count)
        self.identity = u'controller-worker{}'.format(self._id)
        self.core_backend_address = core_backend_address
        self.controllers = controllers
        # NOTE: we need to look into if we can replace dealer with rep
        self.socket = context.socket(zmq.DEALER)
        self.socket.identity = self.identity.encode('ascii')

        self.is_connected = False

    def run(self):
        """Start worker for controller classes."""
        if not self.connect_to_server():
            print(f"{self.identity} quitting")
            return

        while True:
            self.receive_messages()

    def connect_to_server(self) -> bool:
        """Connect and register to server.

        Returns:
            bool: True if connected.
        """
        self.socket.connect(self.core_backend_address)
        print(
            f"{self.identity} started, connecting to {self.core_backend_address}"
        )

        if self.register_to_server():
            print(f"{self.identity}: Connection established")
            self.is_connected = True
        else:
            print("Connection failure")
        return self.is_connected

    def receive_messages(self):
        """Loop to listen for and respond to incoming messages."""
        try:
            identity, message = self.socket.recv_multipart()
        except KeyboardInterrupt:
            return
        message: dict = jsonapi.loads(message)
        print(f"Worker recieved {message} from {identity}")
        self.process_messages(message)
        message.update({"processed": True})
        outgoing = jsonapi.dumps(message)
        self.socket.send_multipart([identity, outgoing])

    def register_to_server(self):
        """Register self to server for synchronized start.

        Returns:
            bool: True if connection granted.
        """
        self.socket.send(bytes(self.identity, 'utf-8'))
        ready_ping = self.socket.recv()
        return b'' in ready_ping

    def process_messages(self, message: list[dict] | dict):
        """Intermediate step for message processing for list vs single element.

        Args:
            message (list[dict] | dict)
        """
        if isinstance(message, list):
            for msg in message:
                self.process_message(msg)
        else:
            self.process_message(message)

    def process_message(self, message: dict):
        """Process incoming message and update controller.

        Args:
            message (dict)
        """
        controller: str
        attributes: dict

        [(controller, attributes)] = message.items()
        for attribute, new_value in attributes.items():
            old_value = self.controllers[controller][attribute]
            self.controllers[controller][attribute] = new_value
            print(
                f"{controller} controller attribute {attribute} changed to {new_value} "
                f"from {old_value}")

    def __call__(self) -> None:
        return self.run()
