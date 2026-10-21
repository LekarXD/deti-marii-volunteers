from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

class ApiError(Exception):
    def __init__(self, status_code, code, message, field_errors=None, current_version=None, retryable=False):
        self.status_code, self.code, self.message = status_code, code, message
        self.field_errors, self.current_version, self.retryable = field_errors or {}, current_version, retryable

def install_error_handlers(app: FastAPI):
    @app.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError):
        return JSONResponse(status_code=error.status_code, content={"code": error.code, "message": error.message, "field_errors": error.field_errors, "current_version": error.current_version, "retryable": error.retryable, "request_id": getattr(request.state, "request_id", None)})
    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, error: RequestValidationError):
        fields = {".".join(map(str, e["loc"])): e["msg"] for e in error.errors()}
        return await api_error(request, ApiError(422, "validation_error", "Проверьте заполненные поля", fields))
    @app.exception_handler(SQLAlchemyError)
    async def database(request: Request, error: SQLAlchemyError):
        return await api_error(request, ApiError(503, "database_unavailable", "Сервис временно недоступен", retryable=True))
