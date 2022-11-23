import re
from functools import wraps

from django.contrib.auth.models import AnonymousUser
from django.utils.cache import patch_cache_control


def minify(template_source):
    """Alternative to django_template_minifier's minify function"""
    if "<" in template_source and "<pre" not in template_source:
        template_source = re.sub(r"\n+ +", "\n", template_source)
    return template_source


def cache_control_s_maxage(max_age):
    def _cache_controller(viewfunc):
        @wraps(viewfunc)
        def _cache_controlled(request, *args, **kw):
            # anonymise request. Cloudflare ignores the Vary header
            request.user = AnonymousUser
            response = viewfunc(request, *args, **kw)
            patch_cache_control(response, s_max_age=max_age)
            return response

        return _cache_controlled

    return _cache_controller
