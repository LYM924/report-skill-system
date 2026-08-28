"""
路由分发器 - 轻量 URL 路由，不引入第三方依赖

用法:
    from router import router

    @router.route("GET", r"^/api/search$")
    def handle_search(handler, params):
        ...
"""

import re


class Router:
    def __init__(self):
        self._routes = []  # [(method, pattern, func)]

    def route(self, method, path_pattern):
        """装饰器：注册路由"""
        pattern = re.compile(path_pattern)

        def decorator(func):
            self._routes.append((method, pattern, func))
            return func

        return decorator

    def dispatch(self, method, path):
        """分发请求到对应的 handler"""
        for m, pattern, func in self._routes:
            if m == method and pattern.match(path):
                return func
        return None


# 全局单例
router = Router()