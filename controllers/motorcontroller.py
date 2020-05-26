from test import *
from net import *
from controller import *
import time

class MotorController(Controller):
    """ The MotorController class interfaces with the motor drive to obtain
    telemetry.
    """

    def __init__(self, network_manager):
        """ Initializes the MotorController class by registering actions and
        variables.
        """
        super().__init__(network_manager)
        self.testData = TestData()
        self.CANBusController = CANBusNet()  # TODO Complete initialization ASAP
        # self.testData.update()
        self._register_variable("speed", 0, VariableAccess.READWRITE)
        self._register_variable("voltage", 0, VariableAccess.READWRITE)
        self._register_variable("temperature", 0, VariableAccess.READWRITE)
        self._register_variable("RPM", 0, VariableAccess.READWRITE)

    def shutdown(self):
        """ Safely terminates the MotorController instance. """
        super().shutdown()

        self.set_variable("speed", 0)
        self.set_variable("RPM", 0)
        self.set_variable("temperature", 0)
        self.set_variable("voltage", 0)

    def update(self):
        """ Updates the controller to the current data.	"""
        self.set_variable("speed", self.testData.get("speed"))
        self.set_variable("voltage", self.testData.get("voltage"))
        self.set_variable("temperature", self.testData.get("temperature"))
        self.set_variable("RPM", self.testData.get("RPM"))

    def run(self):
        time.sleep(1)
