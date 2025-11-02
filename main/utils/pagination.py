from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

class StandardPagePagination(PageNumberPagination):
    page_size = 20
    page_query_param = "page"
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            "page": self.page.number,
            "page_size": self.get_page_size(self.request),
            "total": self.page.paginator.count,
            "items": data,
        })
