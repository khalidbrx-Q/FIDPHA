from django.utils import timezone
from rest_framework.views import APIView, exception_handler
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated
from fidpha.models import Account, Contract


def custom_exception_handler(exc, context):
    timestamp = timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    if isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        return Response({
            "status": "error",
            "timestamp": timestamp,
            "error": {
                "code": "INVALID_TOKEN",
                "message": "Missing or invalid token"
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
                    "message": "The account_code parameter is missing"
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
                    "message": f"No account found with code {account_code}"
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
                    "message": f"No active contract found for account {account_code}"
                }
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception:
            return Response({
                "status": "error",
                "timestamp": timestamp,
                "error": {
                    "code": "SERVER_ERROR",
                    "message": "An internal server error occurred"
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