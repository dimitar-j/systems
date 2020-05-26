from typing import Tuple, Optional, Callable
from controllerdata import ControllerData, VariableAccess
from abc import ABC
from networkmanager import NetworkManager
from controllererror import ControllerError
import logging as log
import threading
import time

class Controller(ABC):
    """ Controller is an abstract base class that all controller classes
    should inherit from. It provides a set of base functionality, and some
    callbacks to be overridden by the child class.
    """

    def __init__(self, network_manager: NetworkManager):
        """ Initializes the variables and actions dictionaries for the
        Controller.
        """
        log.info("Starting '{0}'.".format(type(self).__name__))
        self.networkManager = network_manager
        self.__variables = {}
        self.__actions = {}
        self.__thread = threading.Thread(target=self.run)
        self.__thread.start()

    def _register_variable(self, name: str, value: any,
                           access: VariableAccess =
                           VariableAccess.READWRITE) -> None:
        """ Registers a new variable for the controller.

        name - String identifier of the variable to register.
        value - The default value of the variable.
        access - A VariableAccess to assign the access state of the variable.
        """
        if name in self.__variables:
            log.error("Cannot register two variables with the same "
                      "name '{0}'".format(name))
            raise Exception(
                "Cannot register two variables with the same name '",
                name, "' in: ", type(self).__name__)
        self.__variables[name] = ControllerData(name=name, value=value,
                                                access=access)
        log.info("Registered controller variable '{0}' with "
                 "{1} access.".format(name, access))

    def set_variable(self, name: str, value: any, bypass: bool = True) -> None:
        """ Sets the value of an existing variable.

        name - String identifier of the variable to change.
        value - New value for the variable.
        bypass - If True, bypasses read/write access restrictions.
        """
        if name not in self.__variables:
            log.error("Data variable '{0}' does not exist.".format(name))
            raise ControllerError("Variable '", name,
                                  "' does not exist on type ",
                                  type(self).__name__)
        if not bypass:
            if self.__variables[value].access == VariableAccess.READ:
                log.error("Data variable '{0}' is read-only.".format(name))
                raise ControllerError("Variable '", name,
                                      "' is read-only, cannot write to it")
        self.__variables[name].value = value

    def has_variable(self, name: str) -> bool:
        """ Returns whether the controller has registered a variable with given
        name.

        name - String identifier for the variable to check for.
        """
        return name in self.__variables

    def has_action(self, name: str) -> bool:
        """ Returns whether the controller has registered an action with
        given name.

        name - String identifier for the action to check for.
        """
        return name in self.__actions

    def get_variable(self, name: str, bypass: bool = False) -> any:
        """ Returns the value of a variable

        name - Name of the variable to look for
        bypass - Bypass read/write access restrictions
        """
        if name not in self.__variables:
            log.error("Data variable '{0}' does not exist.".format(name))
            raise ControllerError("Variable '", name,
                                  "' does not exist on type ",
                                  type(self).__name__)
        if not bypass:
            if self.__variables[name].access == VariableAccess.WRITE:
                log.error("Data variable '{0}' is write-only.".format(name))
                raise ControllerError("Variable '", name,
                                      "' is write-only, cannot read from it")
        return self.__variables[name].value

    def _register_action(self, name: str, callback: Callable) -> None:
        """ Registers a new action function

        name - String identifier of the action to register.
        callback - Callback function for when the action is called.
        """
        if name not in self.__actions:
            log.error("Cannot register two actions with the same name "
                      "'{0}'".format(name))
            raise ControllerError(
                "Cannot register two actions with the same name '",
                name, "' in: ", type(self).__name__)
        if not callable(callback):
            log.error(
                "Registered action '{0}' must be a function.".format(name))
            raise ControllerError("Registered action must be a function: ",
                                  name)
        self.__actions[name] = callback
        log.info("Registered controller action '{0}'.".format(name))

    def perform_action(self, name: str, args: Optional[Tuple[any]]) -> None:
        """ Performs a given action, with given arguments.

        name - String identifier of the action to perform.
        args - Tuple of arguments to pass to the function.
        """
        if name not in self.__actions:
            log.error(
                "Actions with the name '{0}' does not exist.".format(name))
            raise ControllerError("Actions with the name does not exist: ",
                                  name,
                                  " in: ", type(self).__name__)
        self.__actions[name](args=args)

    def run(self):
        while(self.running):
            time.sleep(1)

    def shutdown(self) -> None:
        """ Safely terminates the controller. To be called by super() and
        overridden by classes implementing Controller if needed.
        """

        log.info("Shutting down '{0}'.".format(type(self).__name__))
        self.running = False
        self.thread.join()
