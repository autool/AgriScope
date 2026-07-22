"""业务自定义异常。"""


class AppException(Exception):
    """应用可预期异常基类。"""

    def __init__(self, message: str, code: int) -> None:
        """初始化应用异常。

        Args:
            message: 可安全返回给前端的中文提示。
            code: HTTP 状态码。

        Returns:
            None: 无返回值。
        """
        super().__init__(message)
        self.message = message
        self.code = code


class NotFoundException(AppException):
    """目标资源不存在异常。"""

    def __init__(self, message: str = "未找到符合条件的图斑") -> None:
        """初始化资源不存在异常。

        Args:
            message: 可安全返回给前端的提示。

        Returns:
            None: 无返回值。
        """
        super().__init__(message=message, code=404)


class ValidationException(AppException):
    """业务参数校验异常。"""

    def __init__(self, message: str = "请求参数不合法") -> None:
        """初始化业务参数校验异常。

        Args:
            message: 可安全返回给前端的提示。

        Returns:
            None: 无返回值。
        """
        super().__init__(message=message, code=400)


class PermissionDeniedException(AppException):
    """当前用户无权执行目标业务动作。"""

    def __init__(self, message: str = "当前用户无权执行此操作") -> None:
        """初始化权限不足异常。

        Args:
            message: 可安全返回给前端的权限提示。

        Returns:
            None: 无返回值。
        """
        super().__init__(message=message, code=403)
