from rest_framework import generics, permissions
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.http import HttpResponse
from django.contrib.auth import get_user_model
from .serializers import UserSerializer
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

User = get_user_model()


class UserListView(generics.ListAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]


class UserDetailView(generics.RetrieveAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]


from django.http import HttpResponse

@api_view(['GET'])
@permission_classes([AllowAny])
def hello_world(request):
    """
    A simple hello world endpoint (no authentication required)
    """
    return HttpResponse("Hello World Django!")


@api_view(['GET'])
def api_root(request):
    """
    The entry endpoint of our API
    """
    return Response({
        'hello': 'http://localhost:3001/api/hello/',
        'users': 'http://localhost:3001/api/users/',
    })