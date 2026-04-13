from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from fidpha.models import Account, Contract

from rest_framework.views import exception_handler
from django.utils import timezone


def custom_exception_handler(exc, context):
    timestamp = timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated

    if isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        return Response({
            "status": "error",
            "timestamp": timestamp,
            "error": {
                "code": "INVALID_TOKEN",
                "message": "Token manquant ou invalide"
            }
        }, status=401)

    return exception_handler(exc, context)

class ActiveContractView(APIView):

    def get(self, request, version=None):
        timestamp = timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        account_code = request.query_params.get("account_code")

        if not account_code:
            return Response({
                "status": "error",
                "timestamp": timestamp,
                "error": {
                    "code": "MISSING_PARAMETER",
                    "message": "Le paramètre account_code est manquant"
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            account = Account.objects.get(code=account_code)
        except Account.DoesNotExist:
            return Response({
                "status": "error",
                "timestamp": timestamp,
                "error": {
                    "code": "ACCOUNT_NOT_FOUND",
                    "message": f"Aucun compte trouvé avec le code {account_code}"
                }
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            contract = Contract.objects.get(account=account, status="active")
        except Contract.DoesNotExist:
            return Response({
                "status": "error",
                "timestamp": timestamp,
                "error": {
                    "code": "CONTRACT_NOT_FOUND",
                    "message": f"Aucun contrat actif trouvé pour le compte {account_code}"
                }
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                "status": "error",
                "timestamp": timestamp,
                "error": {
                    "code": "SERVER_ERROR",
                    "message": "Une erreur interne s'est produite"
                }
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        products = []
        for cp in contract.contract_product_set.all():
            products.append({
                "product_id": cp.product.pk,
                "internal_code": cp.product.code,
                "external_designation": cp.external_designation
            })

        return Response({
            "status": "success",
            "timestamp": timestamp,
            "contract": {
                "id": contract.pk,
                "pharmacy": account.name,
                "account_code": account.code,
                "start_date": contract.start_date.strftime("%Y-%m-%d"),
                "end_date": contract.end_date.strftime("%Y-%m-%d"),
                "products": products
            }
        }, status=status.HTTP_200_OK)