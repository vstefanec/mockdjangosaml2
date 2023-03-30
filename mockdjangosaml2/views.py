import logging

from django import forms
from django.conf import settings
from django.contrib import auth
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LogoutView
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.template.response import TemplateResponse

from djangosaml2.signals import post_authenticated
from djangosaml2.utils import get_custom_setting

from mockdjangosaml2.settings import MOCK_SAML2_USERS
from djangosaml2.conf import get_config
from django.urls import reverse
logger = logging.getLogger('djangosaml2')


class MockAuthForm(AuthenticationForm):
    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            if username not in MOCK_SAML2_USERS or \
                MOCK_SAML2_USERS[username]['password']!=password:
                raise forms.ValidationError(
                    self.error_messages['invalid_login'] % {
                        'username': self.username_field.verbose_name
                    })
        return self.cleaned_data


def login(request, config_loader_path=None,
          authorization_error_template='djangosaml2/auth_error.html'):
    """ Mock SAML2 Authorization form. """
    if request.method!="POST":
        came_from = request.GET.get('next', settings.LOGIN_REDIRECT_URL)
        return TemplateResponse(request, 'mockdjangosaml2/login.html',
                                {'form': MockAuthForm(request),
                                 'next': came_from})
    logger.debug('Mock login process started')

    came_from = request.POST.get('next', settings.LOGIN_REDIRECT_URL)
    if not came_from:
        logger.warning('The next parameter exists but is empty')
        came_from = settings.LOGIN_REDIRECT_URL

    if not request.user.is_anonymous:
        try:
            redirect_authenticated_user = \
                        settings.SAML_IGNORE_AUTHENTICATED_USERS_ON_LOGIN
        except AttributeError:
            redirect_authenticated_user = True

        if redirect_authenticated_user:
            return HttpResponseRedirect(came_from)
        else:
            logger.debug('User is already logged in')
            return render(
                request,
                authorization_error_template, {
                    'came_from': came_from,
                }
            )

    logger.debug('Check credentials.')
    form = MockAuthForm(data=request.POST)
    if not form.is_valid():
        return TemplateResponse(request, 'mockdjangosaml2/login.html',
                                {'form': form})
    # authenticate the remote user
    session_info = \
        MOCK_SAML2_USERS[request.POST.get('username')]['session_info']
    request.session['mock_session_info'] = session_info
    request.session['mock_came_from'] = came_from
    request.session.modified = True

    if config_loader_path:
        conf = get_config(config_loader_path, request)
        acs_location = conf
    else:
        acs_location = reverse('saml2_acs')
    return HttpResponseRedirect(acs_location)


def assertion_consumer_service(request,
                               config_loader_path=None,
                               attribute_mapping=None,
                               create_unknown_user=None):

    attribute_mapping = get_custom_setting(
            'SAML_ATTRIBUTE_MAPPING', {'uid': ('username', )})
    create_unknown_user = get_custom_setting(
            'SAML_CREATE_UNKNOWN_USER', True)
    logger.debug('Mock assertion Consumer Service started')

    if callable(attribute_mapping):
        attribute_mapping = attribute_mapping()
    if callable(create_unknown_user):
        create_unknown_user = create_unknown_user()

    session_info = request.session['mock_session_info']
    came_from = request.session['mock_came_from']
    logger.debug('Trying to authenticate the user')
    user = auth.authenticate(request=request,
                             session_info=session_info,
                             attribute_mapping=attribute_mapping,
                             create_unknown_user=create_unknown_user)
    if user is None:
        logger.error('The user is None')
        raise PermissionDenied

    auth.login(request, user)

    logger.debug('Sending the post_authenticated signal')
    post_authenticated.send_robust(sender=user, session_info=session_info)

    logger.debug('Redirecting user to %s' % came_from)
    return HttpResponseRedirect(came_from)


@login_required
def logout(request):
    logger.debug('Mock logout process started')

    next_page = '/'
    if hasattr(settings, 'LOGOUT_REDIRECT_URL'):
        next_page = settings.LOGOUT_REDIRECT_URL
    logger.debug('Performing django_logout with a next_page of %s'
                 % next_page)
    return LogoutView.as_view()(request, next_page=next_page)
