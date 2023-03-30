from django.urls import path
from mockdjangosaml2.views import login, assertion_consumer_service, logout


urlpatterns = [
    path('login/', login, name='saml2_login'),
    path('acs/', assertion_consumer_service, name='saml2_acs'),
    path('logout/', logout, name='saml2_logout'),
]
