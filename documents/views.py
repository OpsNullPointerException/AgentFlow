from django.http import JsonResponse
from django.urls import reverse
from django.urls.resolvers import get_resolver

def debug_urls(request):
    """调试视图，返回所有注册的URL模式"""
    resolver = get_resolver()
    url_patterns = []
    
    for pattern in resolver.url_patterns:
        if hasattr(pattern, 'pattern'):
            url_patterns.append(str(pattern.pattern))
    
    return JsonResponse({
        'request_path': request.path,
        'registered_patterns': url_patterns,
        'trailing_slash_setting': getattr(resolver, 'trailing_slash', 'unknown')
    })
