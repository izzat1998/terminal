import os

from cfgv import ValidationError
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.containers.services.container_storage import (
    ContainerStorageService,
)
from apps.core.choices import ContainerSize, TransportType, ContainerState
from apps.core.models import Container
from apps.core.pagination import LimitOffsetPagination, get_paginated_response
from apps.core.utils import inline_serializer
from apps.customers.models import Company


class ContainerStorageRegisterApi(APIView):
    class ContainerStorageRegisterSerializer(serializers.Serializer):
        container_name = serializers.CharField(max_length=11)
        container_size = serializers.ChoiceField(
            required=True, choices=ContainerSize.choices
        )
        container_state = serializers.ChoiceField(
            required=True, choices=ContainerState.choices
        )
        container_owner = serializers.CharField(required=True, allow_blank=True)
        product_name = serializers.CharField(
            required=True, allow_null=True, allow_blank=True
        )
        transport_type = serializers.ChoiceField(
            required=True, choices=TransportType.choices
        )
        transport_number = serializers.CharField(required=True, allow_blank=True)
        company_id = serializers.IntegerField(required=True)
        entry_time = serializers.DateTimeField(required=True)
        notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
        services = inline_serializer(
            fields={
                "id": serializers.IntegerField(),
                "date_from": serializers.DateTimeField(required=False),
                "date_to": serializers.DateTimeField(required=False, allow_null=True),
            },
            many=True,
            required=True,
        )

        def validate_container_size(self, container_size: str) -> str:
            if container_size not in dict(ContainerSize.choices).keys():
                raise serializers.ValidationError("Invalid container size")
            return container_size

        def validate_container_name(self, container_name: str) -> str:
            container = Container.objects.filter(name=container_name).first()
            if container and container.in_storage:
                raise serializers.ValidationError(
                    "Container is already in storage",
                )
            return container_name

        def validate_company_id(self, company_id: int) -> int:
            if not Company.objects.filter(id=company_id).first():
                raise serializers.ValidationError("Customer does not exist")
            return company_id

    class ContainerStorageRegisterOutputSerializer(serializers.Serializer):
        id = serializers.IntegerField(read_only=True)
        container = inline_serializer(
            fields={
                "id": serializers.IntegerField(read_only=True),
                "name": serializers.CharField(read_only=True),
                "size": serializers.CharField(read_only=True),
            }
        )
        container_state = serializers.CharField(read_only=True)
        transport_type = serializers.CharField(read_only=True)
        transport_number = serializers.CharField(read_only=True)
        product_name = serializers.CharField(read_only=True)
        container_owner = serializers.CharField(read_only=True)

        company = inline_serializer(
            fields={
                "id": serializers.IntegerField(read_only=True),
                "name": serializers.CharField(read_only=True),
            }
        )
        entry_time = serializers.DateTimeField(read_only=True)
        notes = serializers.CharField(read_only=True)

    @extend_schema(
        summary="Register container entry",
        request=ContainerStorageRegisterSerializer,
        responses=ContainerStorageRegisterOutputSerializer,
    )
    def post(self, request):
        serializer = self.ContainerStorageRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        container = ContainerStorageService().register_container_entry(
            serializer.validated_data
        )
        return Response(
            self.ContainerStorageRegisterOutputSerializer(container).data,
            status=status.HTTP_201_CREATED,
        )


class ContainerStorageRegisterBatchApi(APIView):
    class ContainerStorageImportExcelSerializer(serializers.Serializer):
        container_name = serializers.CharField(max_length=11)
        container_size = serializers.ChoiceField(
            required=True, choices=ContainerSize.choices
        )
        company_name = serializers.CharField(required=True)
        container_state = serializers.CharField(required=True)
        container_owner = serializers.CharField(required=True, allow_blank=True)
        product_name = serializers.CharField(required=False, allow_blank=True)
        transport_type = serializers.CharField(required=True)
        transport_number = serializers.CharField(required=True, allow_blank=True)
        entry_time = serializers.DateTimeField(required=True)
        exit_time = serializers.DateTimeField(required=False, allow_null=True)
        dispatch_method = serializers.CharField(required=False, allow_blank=True)

        def validate_container_size(self, container_size: str) -> str:
            if container_size not in dict(ContainerSize.choices).keys():
                raise serializers.ValidationError("Invalid container size")
            return container_size

        def validate_container_state(self, container_state: str) -> str:
            if container_state.lower() not in [
                "порожний",
                "груженый",
                "empty",
                "loaded",
            ]:
                raise serializers.ValidationError("Invalid container state")
            return container_state

        def validate_transport_type(self, transport_type: str) -> str:
            if transport_type.lower() not in ["авто", "вагон", "auto", "wagon"]:
                raise serializers.ValidationError("Invalid transport type")
            return transport_type

        def validate_company_name(self, company_name: str) -> str:
            if not Company.objects.filter(name=company_name).exists():
                raise serializers.ValidationError("Customer does not exist")
            return company_name

    def get(self, request):
        file_path = os.path.join("./apps/utils", "import_excel_mtt.xlsx")
        with open(file_path, "rb") as excel_file:
            response = HttpResponse(
                excel_file.read(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response["Content-Disposition"] = "attachment; filename=template.xlsx"
            return response

    def post(self, request):
        serializer = self.ContainerStorageImportExcelSerializer(
            data=request.data, many=True
        )

        try:
            serializer.is_valid(raise_exception=True)
            service = ContainerStorageService()
            service.register_container_batch_entry(serializer.validated_data)
            return Response(status=status.HTTP_201_CREATED)
        except ValidationError as e:
            if hasattr(e, "detail") and isinstance(e.detail, dict):
                error_response = {
                    "message": "Validation error",
                    "extra": {"fields": e.detail.get("fields", [])},
                    "fields": e.detail.get("fields", []),
                }
            else:
                # Handle serializer validation errors
                error_response = {
                    "message": "Validation error",
                    "extra": {
                        "fields": [
                            {k: v} if v else {} for k, v in enumerate(serializer.errors)
                        ]
                    },
                    "fields": [
                        {k: v} if v else {} for k, v in enumerate(serializer.errors)
                    ],
                }
            return Response(error_response, status=status.HTTP_400_BAD_REQUEST)


class ContainerStorageUpdateApi(APIView):
    permission_classes = [IsAuthenticated]

    class ContainerStorageUpdateSerializer(serializers.Serializer):
        container_name = serializers.CharField(max_length=11, required=True)
        container_size = serializers.ChoiceField(
            choices=ContainerSize.choices, required=True
        )
        container_state = serializers.ChoiceField(
            choices=ContainerState.choices, required=False
        )
        container_owner = serializers.CharField(required=False)
        transport_type = serializers.ChoiceField(
            choices=TransportType.choices, required=False
        )
        product_name = serializers.CharField(
            required=False, allow_blank=True, allow_null=True
        )
        transport_number = serializers.CharField(required=False)
        exit_transport_type = serializers.ChoiceField(
            choices=TransportType.choices, required=False, allow_blank=True
        )
        exit_transport_number = serializers.CharField(
            required=False, allow_blank=True, allow_null=True
        )
        company_id = serializers.IntegerField(required=True)
        entry_time = serializers.DateTimeField(required=False)
        exit_time = serializers.DateTimeField(required=False, allow_null=True)
        notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)

        def validate_company_id(self, value):
            if not Company.objects.filter(id=value).exists():
                raise serializers.ValidationError("Customer does not exist")
            return value

    class ContainerStorageUpdateOutputSerializer(serializers.Serializer):
        company = inline_serializer(
            fields={
                "id": serializers.IntegerField(read_only=True),
                "name": serializers.CharField(read_only=True),
            }
        )

    @extend_schema(
        summary="Update container visit",
        request=ContainerStorageUpdateSerializer,
        responses=ContainerStorageUpdateOutputSerializer,
    )
    def put(self, request, visit_id):
        serializer = self.ContainerStorageUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        container_visit = ContainerStorageService().update_container_visit(
            visit_id, serializer.validated_data
        )
        return Response(
            self.ContainerStorageUpdateOutputSerializer(container_visit).data,
            status=status.HTTP_200_OK,
        )


class ContainerStorageDeleteApi(APIView):
    permission_classes = [IsAuthenticated]

    class ContainerStorageDeleteSerializer(serializers.Serializer):
        pass

    @extend_schema(
        summary="Delete container visit", responses=ContainerStorageDeleteSerializer
    )
    def delete(self, request, visit_id):
        ContainerStorageService().delete(visit_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ContainerStorageListApi(APIView):
    class Pagination(LimitOffsetPagination):
        default_limit = 10
        max_limit = 100

    class FilterSerializer(serializers.Serializer):
        types = serializers.CharField(
            required=False,
        )
        company_name = serializers.CharField(required=False)
        container_name = serializers.CharField(required=False)
        container_size = serializers.CharField(required=False)
        container_state = serializers.ChoiceField(
            choices=ContainerState.choices, required=False
        )
        product_name = serializers.CharField(required=False)
        container_owner = serializers.CharField(required=False)
        transport_type = serializers.CharField(required=False)
        transport_number = serializers.CharField(required=False)
        exit_transport_type = serializers.CharField(required=False)
        exit_transport_number = serializers.CharField(required=False)
        active_services = serializers.CharField(required=False)
        dispatch_services = serializers.CharField(required=False)
        exit_time = serializers.CharField(required=False)
        entry_time = serializers.CharField(required=False)
        storage_days = serializers.IntegerField(required=False)
        notes = serializers.CharField(required=False)

    class ContainerStorageListSerializer(serializers.Serializer):
        id = serializers.IntegerField(read_only=True)
        container = inline_serializer(
            fields={
                "id": serializers.IntegerField(read_only=True),
                "name": serializers.CharField(read_only=True),
                "size": serializers.CharField(
                    source="get_size_display", read_only=True
                ),
            }
        )
        company = inline_serializer(
            fields={
                "id": serializers.IntegerField(read_only=True),
                "name": serializers.CharField(read_only=True),
            }
        )
        images = inline_serializer(
            fields={
                "id": serializers.IntegerField(read_only=True),
                "image": serializers.ImageField(read_only=True),
                "name": serializers.CharField(read_only=True),
            },
            many=True,
        )
        product_name = serializers.CharField(read_only=True)
        container_owner = serializers.CharField(read_only=True)
        transport_type = serializers.CharField(read_only=True)
        transport_number = serializers.CharField(read_only=True)
        exit_transport_type = serializers.CharField(read_only=True)
        exit_transport_number = serializers.CharField(read_only=True)
        documents = inline_serializer(
            fields={
                "id": serializers.IntegerField(read_only=True),
                "document": serializers.FileField(read_only=True),
                "name": serializers.CharField(read_only=True),
            },
            many=True,
        )

        container_state = serializers.CharField(read_only=True)
        entry_time = serializers.DateTimeField(read_only=True)
        exit_time = serializers.DateTimeField(read_only=True)
        storage_days = serializers.IntegerField(read_only=True)
        notes = serializers.CharField(read_only=True)
        free_days = serializers.IntegerField(
            read_only=True, source="contract.free_days"
        )
        services = serializers.SerializerMethodField(method_name="get_services")

        def get_services(self, obj):
            services = []
            for service in obj.services.all():
                services.append(
                    {
                        "id": service.id,
                        "date_from": service.date_from,
                        "date_to": service.date_to,
                        "notes": service.notes,
                        "performed_at": service.performed_at,
                        "service_type": {
                            "id": service.contract_service.service.service_type.id,
                            "name": service.contract_service.service.service_type.name,
                            "unit_of_measure": service.contract_service.service.service_type.unit_of_measure,
                        },
                        "base_price": service.contract_service.service.base_price,
                        "price": service.contract_service.price,
                    }
                )
            return services

    @extend_schema(
        summary="List container visits",
        responses=ContainerStorageListSerializer,
        parameters=[
            OpenApiParameter(
                name="status",
                type=str,
                enum=["in_terminal", "left_terminal", "all"],
                default="all",
            )
        ],
    )
    def get(self, request):
        filters_serializer = self.FilterSerializer(data=request.query_params)
        filters_serializer.is_valid(raise_exception=True)
        container_storages = ContainerStorageService().get_all_containers_visits(
            filters=filters_serializer.validated_data
        )
        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=self.ContainerStorageListSerializer,
            queryset=container_storages,
            request=request,
            view=self,
        )


class ContainerStorageDetailApi(APIView):
    class ContainerStorageDetailSerializer(serializers.Serializer):
        id = serializers.IntegerField(read_only=True)
        container = inline_serializer(
            fields={
                "id": serializers.IntegerField(read_only=True),
                "name": serializers.CharField(read_only=True),
                "size": serializers.CharField(read_only=True),
            }
        )
        company = inline_serializer(
            fields={
                "id": serializers.IntegerField(read_only=True),
                "name": serializers.CharField(read_only=True),
            }
        )
        images = inline_serializer(
            fields={
                "id": serializers.IntegerField(read_only=True),
                "image": serializers.ImageField(read_only=True),
                "name": serializers.CharField(read_only=True),
            },
            many=True,
        )
        product_name = serializers.CharField(read_only=True)
        container_owner = serializers.CharField(read_only=True)
        transport_type = serializers.CharField(read_only=True)
        transport_number = serializers.CharField(read_only=True)
        exit_transport_type = serializers.CharField(read_only=True)
        exit_transport_number = serializers.CharField(read_only=True)
        documents = inline_serializer(
            fields={
                "id": serializers.IntegerField(read_only=True),
                "document": serializers.FileField(read_only=True),
                "name": serializers.CharField(read_only=True),
            },
            many=True,
        )

        container_state = serializers.CharField(read_only=True)
        entry_time = serializers.DateTimeField(read_only=True)
        exit_time = serializers.DateTimeField(read_only=True)
        storage_days = serializers.IntegerField(read_only=True)
        notes = serializers.CharField(read_only=True)
        free_days = serializers.IntegerField(
            read_only=True, source="contract.free_days"
        )
        services = serializers.SerializerMethodField(method_name="get_services")

        def get_services(self, obj):
            services = []
            for service in obj.services.all():
                services.append(
                    {
                        "id": service.id,
                        "date_from": service.date_from,
                        "date_to": service.date_to,
                        "notes": service.notes,
                        "performed_at": service.performed_at,
                        "service_type": {
                            "id": service.contract_service.service.service_type.id,
                            "name": service.contract_service.service.service_type.name,
                            "unit_of_measure": service.contract_service.service.service_type.unit_of_measure,
                        },
                        "base_price": service.contract_service.service.base_price,
                        "price": service.contract_service.price,
                    }
                )
            return services

    @extend_schema(
        summary="Get container visit details",
        responses=ContainerStorageDetailSerializer,
    )
    def get(self, request, visit_id):
        container_storage_service = ContainerStorageService()
        container_storage = container_storage_service.get_container_visit(visit_id)
        return Response(
            self.ContainerStorageDetailSerializer(container_storage).data,
            status=status.HTTP_200_OK,
        )


class ContainerStorageDispatchApi(APIView):
    class ContainerStorageExitSerializer(serializers.Serializer):
        id = serializers.IntegerField(read_only=True)
        exit_time = serializers.DateTimeField(required=True)
        exit_transport_type = serializers.ChoiceField(
            choices=TransportType.choices, required=True
        )
        exit_transport_number = serializers.CharField(required=True)

    @extend_schema(
        summary="Dispatch container visit",
        request=ContainerStorageExitSerializer,
    )
    def put(self, request, visit_id):
        serializer = self.ContainerStorageExitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        container_storage = ContainerStorageService().dispatch_container_visit(
            visit_id, serializer.validated_data
        )
        return Response(
            ContainerStorageDetailApi.ContainerStorageDetailSerializer(
                container_storage
            ).data,
            status=status.HTTP_200_OK,
        )


class ContainerStorageAvailableServicesApi(APIView):
    class ContainerStorageAvailableServicesSerializer(serializers.Serializer):
        pass

    class ContainerStorageAvailableServicesOutputSerializer(serializers.Serializer):
        id = serializers.IntegerField(read_only=True)
        name = serializers.CharField(source="service.name", read_only=True)
        description = serializers.CharField(
            read_only=True, source="service.description"
        )
        container_size = serializers.CharField(
            source="service.container_size", read_only=True
        )
        container_state = serializers.CharField(
            source="service.container_state", read_only=True
        )

        service_type = inline_serializer(
            fields={
                "id": serializers.IntegerField(read_only=True),
                "name": serializers.CharField(read_only=True),
                "unit_of_measure": serializers.CharField(read_only=True),
            },
            source="service.service_type",
        )
        base_price = serializers.DecimalField(
            source="service.base_price", read_only=True, max_digits=10, decimal_places=2
        )
        multiple_usage = serializers.BooleanField(
            source="service.multiple_usage", read_only=True
        )
        price = serializers.DecimalField(
            read_only=True, max_digits=10, decimal_places=2
        )

    @extend_schema(
        summary="Get available services for container visit",
        responses=ContainerStorageAvailableServicesOutputSerializer,
    )
    def get(self, request, visit_id):
        services = ContainerStorageService().get_available_services(visit_id)
        return Response(
            self.ContainerStorageAvailableServicesOutputSerializer(
                services, many=True
            ).data
        )


class ContainerStorageListByCustomerApi(APIView):
    class Pagination(LimitOffsetPagination):
        default_limit = 10
        max_limit = 100

    class FilterSerializer(serializers.Serializer):
        types = serializers.CharField(
            required=False,
        )
        company = serializers.CharField(required=False)
        is_empty = serializers.BooleanField(required=False, allow_null=True)
        container = serializers.CharField(required=False)
        status = serializers.ChoiceField(
            choices=["in_terminal", "left_terminal", "all"],
            required=False,
            default="all",
        )
        entry_time = serializers.DateField(required=False)
        storage_days = serializers.IntegerField(required=False)
        notes = serializers.CharField(required=False)

    class ContainerStorageByCustomerListSerializer(serializers.Serializer):
        container = inline_serializer(
            fields={
                "id": serializers.IntegerField(read_only=True),
                "name": serializers.CharField(read_only=True),
                "type": serializers.CharField(
                    source="get_type_display", read_only=True
                ),
            }
        )
        company = inline_serializer(
            fields={
                "id": serializers.IntegerField(read_only=True),
                "name": serializers.CharField(read_only=True),
            }
        )
        images = inline_serializer(
            fields={
                "id": serializers.IntegerField(read_only=True),
                "image": serializers.ImageField(read_only=True),
                "name": serializers.CharField(read_only=True),
            },
            many=True,
        )
        documents = inline_serializer(
            fields={
                "id": serializers.IntegerField(read_only=True),
                "document": serializers.FileField(read_only=True),
                "name": serializers.CharField(read_only=True),
            },
            many=True,
        )

        is_empty = serializers.BooleanField(read_only=True)
        entry_time = serializers.DateTimeField(read_only=True)
        exit_time = serializers.DateTimeField(read_only=True)
        storage_days = serializers.IntegerField(read_only=True)
        notes = serializers.CharField(read_only=True)
        total_storage_cost = serializers.DecimalField(
            max_digits=10, decimal_places=2, read_only=True
        )
        active_services = inline_serializer(
            fields={
                "id": serializers.IntegerField(),
                "name": serializers.CharField(source="service.name"),
                "service_type": serializers.CharField(
                    source="service.service_type.name"
                ),
                "container_size": serializers.CharField(
                    source="service.container_size"
                ),
                "price": serializers.DecimalField(max_digits=10, decimal_places=2),
            },
            many=True,
        )

    @extend_schema(
        summary="List container visits",
        responses=ContainerStorageByCustomerListSerializer,
        parameters=[
            OpenApiParameter(
                name="status",
                type=str,
                enum=["in_terminal", "left_terminal", "all"],
                default="all",
            )
        ],
    )
    def get(self, request, company_id):
        filters_serializer = self.FilterSerializer(data=request.query_params)
        filters_serializer.is_valid(raise_exception=True)
        container_storage_service = ContainerStorageService()
        container_storages = (
            container_storage_service.get_all_containers_visits_by_company(
                company_id=company_id, filters=filters_serializer.validated_data
            )
        )
        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=self.ContainerStorageByCustomerListSerializer,
            queryset=container_storages,
            request=request,
            view=self,
        )
