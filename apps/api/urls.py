from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny
from rest_framework.routers import APIRootView, DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

from . import views

app_name = 'api'


class PublicAPIRootView(APIRootView):
    permission_classes = [AllowAny]


router = DefaultRouter()
router.APIRootView = PublicAPIRootView
router.register('categories', views.ResourceCategoryViewSet, basename='category')
router.register('resources', views.ResourceViewSet, basename='resource')
router.register('bookings', views.BookingViewSet, basename='booking')
router.register('cart', views.CartItemViewSet, basename='cart')
router.register('orders', views.OrderViewSet, basename='order')
router.register('users', views.UserViewSet, basename='user')

urlpatterns = [
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='api:schema'), name='docs'),
    path('', include(router.urls)),
]
