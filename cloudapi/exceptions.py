from rest_framework.exceptions import APIException
from rest_framework import status

class BusinessLogicError(APIException):
    """
    Excepción base para errores de reglas de negocio.
    Devolverá un HTTP 400 Bad Request.
    """
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Error en la lógica de negocio.'
    default_code = 'business_error'

class CommitmentAlreadyExecutedError(BusinessLogicError):
    """
    Se intenta ejecutar un compromiso que ya estaba completado.
    """
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Este compromiso ya fue ejecutado previamente.'
    default_code = 'commitment_already_executed'

class RelatedRequestNotFoundError(BusinessLogicError):
    """
    No se encuentra el Pedido (Request) asociado a un Compromiso.
    """
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = 'No se encontró el pedido de colaboración asociado a este compromiso.'
    default_code = 'request_not_found'
