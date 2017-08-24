"""
Implements an XMLRPC dispatcher
"""

import datetime
try:
    # Python2
    from xmlrpclib import Fault, dumps, Marshaller
    from SimpleXMLRPCServer import SimpleXMLRPCDispatcher
except ImportError:
    # Python3
    from xmlrpc.client import Fault, dumps, Marshaller
    from xmlrpc.server import SimpleXMLRPCDispatcher

import inspect
from defusedxml import xmlrpc

from collections import OrderedDict
Marshaller.dispatch[OrderedDict] = Marshaller.dump_struct


# Transparently support datetime.date as datetime.datetime
def dump_date(instance, value, write):
    value = datetime.datetime.combine(value, datetime.time.min)
    return Marshaller.dump_datetime(instance, value, write)


Marshaller.dispatch[datetime.date] = dump_date

# This method makes the XMLRPC parser (used by loads) safe
# from various XML based attacks
xmlrpc.monkey_patch()


class XMLRPCDispatcher(SimpleXMLRPCDispatcher):
    """
    Encodes and decodes XMLRPC messages, dispatches to the requested method
    and returns any responses or errors in encoded XML.

    Subclasses SimpleXMLRPCDispatcher so that it can
    also pass the Django HttpRequest object from the underlying RPC request
    """

    def __init__(self):
        self.funcs = {}
        self.instance = None
        self.allow_none = True
        self.encoding = None

    def dispatch(self, data, **kwargs):
        """
        Extracts the xml marshaled parameters and method name and calls the
        underlying method and returns either an xml marshaled response
        or an XMLRPC fault

        Although very similar to the superclass' _marshaled_dispatch, this
        method has a different name due to the different parameters it takes
        from the superclass method.
        """
        try:
            params, method = xmlrpc.xmlrpc_client.loads(data)
            response = self._dispatch(method, params, **kwargs)

            # wrap response in a singleton tuple
            response = (response,)
            response = dumps(response, methodresponse=1,
                             allow_none=self.allow_none,
                             encoding=self.encoding)
        except Fault as fault:
            response = dumps(fault, allow_none=self.allow_none,
                             encoding=self.encoding)
        except Exception:
            response = dumps(
                Fault(1, 'Unknown error'),
                encoding=self.encoding, allow_none=self.allow_none,
            )

        return response

    def _dispatch(self, method, params, **kwargs):
        """
        Dispatches the method with the parameters to the underlying method
        """

        func = self.funcs.get(method, None)
        # add some magic
        # if request is the first arg of func and request is provided in kwargs we inject it
        args = inspect.getargspec(func)[0]
        if args and args[0] == 'self':
            args = args[1:]
        if 'request' in kwargs and args and args[0] == 'request':
            request = kwargs.pop('request')
            params = (request,) + params
        if func is not None:
            try:
                return func(*params, **kwargs)
            except TypeError:
                # Catch unexpected keyword argument error
                return func(*params)
        else:
            raise Exception('method "%s" is not supported' % method)
