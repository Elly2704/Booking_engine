import time
import logging

logger = logging.getLogger('django')


class RequestTimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()
        response = self.get_response(request)
        duration = time.time() - start_time
        logger.info(f"Request {request.path} processed in {duration:.4f}s")
        return response