def accounts_badge(request):
    from fidpha.models import Account
    active = Account.objects.filter(status='active').count()
    total = Account.objects.count()
    return f"{active}/{total}"


def contracts_badge(request):
    from fidpha.models import Contract
    active = Contract.objects.filter(status='active').count()
    total = Contract.objects.count()
    return f"{active}/{total}"


def products_badge(request):
    from fidpha.models import Product
    active = Product.objects.filter(status='active').count()
    total = Product.objects.count()
    return f"{active}/{total}"


def users_badge(request):
    from django.contrib.auth.models import User
    return User.objects.count()