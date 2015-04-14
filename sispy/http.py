# -*- coding: utf-8 -*-

import logging
import sys

# attempt to use requests by default, if not available fall back to the 
# standard library
try:
    import requests
except ImportError:
    HTTP_LIB = 'stdlib'
else:
    HTTP_LIB = 'requests'

if HTTP_LIB == 'stdlib':
    # for versions 2.7.9+ and 3.4.3+ we need unverified SSL context to disable
    # SSL cer validation on per request basis
    SSL_CONTEXT = None
    import ssl
    if hasattr(ssl, '_create_unverified_context'):
        SSL_CONTEXT = ssl._create_unverified_context()

    # py3
    if sys.version_info.major >= 3:
        import urllib.request, urllib.error
        stdlib_request = urllib.request.Request
        stdlib_HTTPError = urllib.error.HTTPError   
        stdlib_urlopen = urllib.request.urlopen

    # py2
    else:
        import urllib
        import urllib2
        stdlib_request = urllib2.Request
        stdlib_HTTPError = urllib2.HTTPError
        stdlib_urlopen = urllib2.urlopen

elif HTTP_LIB == 'requests':
    # this will disable InsecureRequestWarning
    requests.packages.urllib3.disable_warnings()

# urlencode method
if sys.version_info.major >= 3:
    import urllib.parse
    urlencode = urllib.parse.urlencode
else:
    import urllib
    urlencode = urllib.urlencode

from . import json, Response, Error, Meta

LOG = logging.getLogger(__name__)

def get_handler():
    """Returns an appropriate http handler object based on the available 
    http library.

    """
    if HTTP_LIB == 'stdlib':    
        return StdLibHandler()

    elif HTTP_LIB == 'requests':
        return RequestsHandler()

class Request(object):

    """HTTP request proxy"""

    def __init__(self, uri, method='GET', body=None, headers=None):
        self.uri = uri
        self.method = method
        self.body = body
        self.headers = headers

    def __str__(self):
        s = ''
        s += '{} '.format(self.method)
        s += '{} '.format(self.uri)
        return s

class BaseHTTPHandler(object):

    """HTTP Handler proxy base class"""

    def __init__(self):
        pass

    def request(self, request):
        raise NotImplementedError

class StdLibHandler(BaseHTTPHandler):

    """Handles http using the standard library"""

    def __init__(self, *args, **kwargs): 
        super(StdLibHandler, self).__init__(*args, **kwargs)

    def request(self, request):
        # encode request.body (py3)
        # POST data should be bytes or an iterable of bytes.
        if request.body:
            request.body = request.body.encode('utf-8')

        # create Request() object, set uri and body contents if any
        new_req = stdlib_request(request.uri, data=request.body)

        # add headers if present
        if request.headers:
            for header_name in request.headers:
                new_req.add_header(header_name, request.headers[header_name])

        # set method, if different from GET
        if request.method != 'GET':
            # urllib method needs to be a callable method
            new_req.get_method = lambda: request.method

        # send request
        LOG.debug(request)
        try:
            # if SSL_CONTEXT is set urlopen is assumed to support context arg
            if SSL_CONTEXT:
                response = stdlib_urlopen(new_req, context=SSL_CONTEXT)
            else:
                response = stdlib_urlopen(new_req)

        except stdlib_HTTPError as e:
            response_dict = json.loads(e.read().decode('utf-8'))
            code = response_dict.get('code')

            # lookup error in the response body,
            # if not available use http error info
            error = response_dict.get('error')
            if not error:
                error = e.reason

            raise Error(http_status_code=e.code,
                        error=error,
                        code=code,
                        response_dict=response_dict)

        # read response
        result = json.loads(response.read().decode('utf-8'))

        # build meta with headers as a dict
        # py3
        if sys.version_info.major >= 3:
            # python2.6 does not support dict comprehensions
            d = {}
            for k, v in response.info().items():
                d[k] = v
            meta = Meta(d)

        # py2
        else:
            meta = Meta(response.info().dict)

        # return Response object    
        return Response(result, meta)

class RequestsHandler(BaseHTTPHandler):

    """Handles HTTP using requests library"""          

    def __init__(self, *args, **kwargs):
        super(RequestsHandler, self).__init__(*args, **kwargs)

        self._session = requests.Session()
        
    def request(self, request):
        LOG.debug(request)

        # prepare request
        req = requests.Request(request.method, request.uri, 
                               data=request.body, headers=request.headers)
        prepped = self._session.prepare_request(req)

        # send request
        # stream=True immediately download the response 
        # content(default is False)
        # verify=False do not verify SSL cert
        response = self._session.send(prepped, stream=True, verify=False)

        # we always expect a json body
        response_dict = json.loads(response.text)

        # raise Error if we got http status code >= 400
        if response.status_code >= 400:
            # lookup error and code in the response dict
            error = response_dict.get('error')
            code = response_dict.get('code')

            raise Error(http_status_code=response.status_code,
                        error=error,
                        code=code,
                        response_dict=response_dict)

        # create Meta
        meta = Meta(response.headers)
        
        # return Response()
        return Response(response_dict, meta)

