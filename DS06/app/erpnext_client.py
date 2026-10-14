import json
import os
from dotenv import load_dotenv
load_dotenv()
from typing import Any, Dict, List, Optional

import requests


class ERPNextClient:
    def __init__(self):
        self.base_url = os.getenv("ERPNEXT_BASE_URL", "").rstrip("/")
        self.api_key = os.getenv("ERPNEXT_API_KEY", "")
        self.api_secret = os.getenv("ERPNEXT_API_SECRET", "")

        if not self.base_url:
            raise ValueError("ERPNEXT_BASE_URL is not configured")
        if not self.api_key or not self.api_secret:
            raise ValueError(
                "ERPNEXT_API_KEY / ERPNEXT_API_SECRET are not configured"
            )

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"token {self.api_key}:{self.api_secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_doc(self, doctype: str, name: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/resource/{doctype}/{name}"

        r = requests.get(
            url,
            headers=self.headers,
            timeout=30,
        )
        r.raise_for_status()

        return r.json()["data"]

    def update_doc(
    self,
    doctype: str,
    name: str,
    fields: Dict[str, Any],
    ) -> Dict[str, Any]:

        url = f"{self.base_url}/api/resource/{doctype}/{name}"

        r = requests.put(
            url,
            headers=self.headers,
            json={"data": fields},
            timeout=30,
        )

        if not r.ok:
            raise RuntimeError(
                f"ERPNext PUT failed: "
                f"status={r.status_code}, "
                f"url={url}, "
                f"response={r.text}"
            )

        return r.json()["data"]

    def list_docs(
        self,
        doctype: str,
        fields: Optional[List[str]] = None,
        filters: Optional[List[List[Any]]] = None,
        limit_page_length: int = 0,
        parent: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generic ERPNext REST list endpoint.

        For child tables such as Discipline Allocation,
        parent="Design Discipline Assignment" is required.
        """

        url = f"{self.base_url}/api/resource/{doctype}"

        params: Dict[str, Any] = {
            "limit_page_length": limit_page_length,
        }

        if fields:
            params["fields"] = json.dumps(fields)

        if filters:
            params["filters"] = json.dumps(filters)

        if parent:
            params["parent"] = parent

        r = requests.get(
            url,
            headers=self.headers,
            params=params,
            timeout=120,
        )
        r.raise_for_status()

        return r.json()["data"]

    # ------------------------------------------------------------------
    # Delay Risk data sources
    # ------------------------------------------------------------------

    def get_projects(self) -> List[Dict[str, Any]]:
        return self.list_docs(
            "Project",
            fields=[
                "name",
                "project_type",
                "expected_start_date",
                "expected_end_date",
                "customer",
            ],
        )

    def get_design_discipline_assignments(self) -> List[Dict[str, Any]]:
        return self.list_docs(
            "Design Discipline Assignment",
            fields=[
                "name",
                "project",
                "project_manager",
            ],
        )

    def get_discipline_allocations(self) -> List[Dict[str, Any]]:
        return self.list_docs(
            "Discipline Allocation",
            fields=[
                "name",
                "parent",
                "employee",
                "discipline",
                "workload_percent",
                "planned_hours",
                "start_date",
                "end_date",
                "actual_hours",
                "actual_close_date",
            ],
            parent="Design Discipline Assignment",
        )

    def get_sales_orders(self) -> List[Dict[str, Any]]:
        return self.list_docs(
            "Sales Order",
            fields=[
                "project",
                "grand_total",
                "docstatus",
            ],
            filters=[
                ["docstatus", "=", 1],
            ],
        )

    def get_tasks(self) -> List[Dict[str, Any]]:
        return self.list_docs(
            "Task",
            fields=[
                "name",
                "project",
                "status",
                "exp_end_date",
                "completed_on",
            ],
        )

    def get_employees(self) -> List[Dict[str, Any]]:
        return self.list_docs(
            "Employee",
            fields=[
                "name",
                "status",
            ],
        )

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def get_project_bundle(self, project_name: str) -> Dict[str, Any]:
        """
        Fetch all raw ERPNext data required for Delay Risk.

        This method intentionally returns raw data only.
        Feature engineering is kept outside the client.
        """

        return {
            # Project đang được score
            "project": self.get_doc(
                "Project",
                project_name,
            ),

            # Toàn bộ project để feature_builder có thể
            "projects": self.get_projects(),

            "assignments": self.get_design_discipline_assignments(),
            "allocations": self.get_discipline_allocations(),
            "sales_orders": self.get_sales_orders(),
            "tasks": self.get_tasks(),
            "employees": self.get_employees(),
        }
    def get_opportunity_bundle(
    self,
    opportunity_name: str,
    ) -> Dict[str, Any]:

        opportunity = self.get_doc(
            "Opportunity",
            opportunity_name,
        )

        quotations = self.list_docs(
            "Quotation",
            filters=[
                [
                    "opportunity",
                    "=",
                    opportunity_name,
                ]
            ],
            fields=[
                "name",
                "opportunity",
                "transaction_date",
                "additional_discount_percentage",
            ],
        )

        leads = self.list_docs(
            "Lead",
            fields=[
                "name",
                "creation",
            ],
        )

        return {
            "opportunity": opportunity,
            "quotations": quotations,
            "leads": leads,
        }
    def get_custom_field_options(
    self,
    doctype: str,
    fieldname: str,
    ) -> Dict[str, Any]:

        rows = self.list_docs(
            "Custom Field",
            fields=[
                "name",
                "dt",
                "fieldname",
                "fieldtype",
                "options",
            ],
            filters=[
                ["dt", "=", doctype],
                ["fieldname", "=", fieldname],
            ],
        )

        if not rows:
            raise ValueError(
                f"Không tìm thấy Custom Field "
                f"{doctype}.{fieldname}"
            )

        return rows[0]