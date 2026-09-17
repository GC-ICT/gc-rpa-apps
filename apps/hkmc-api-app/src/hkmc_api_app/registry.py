from __future__ import annotations

from collections.abc import Iterable

from hkmc_api_app import api_001_daily_demand as api_001
from hkmc_api_app import api_002_weekly_demand as api_002
from hkmc_api_app import api_003_parts_shipment_info as api_003
from hkmc_api_app import api_004_production_performance as api_004
from hkmc_api_app import api_005_supplier_inventory as api_005
from hkmc_api_app import api_006_paid_supplied_inventory as api_006
from hkmc_api_app import api_007_realtime_shortage as api_007
from hkmc_api_app import api_008_parts_retro_result as api_008
from hkmc_api_app import api_009_parts_shipment_creation as api_009
from hkmc_api_app import api_010_supplier_inventory_adjustment as api_010
from hkmc_api_app import api_011_paid_supplied_inventory_stock_result as api_011
from hkmc_api_app import api_012_material_master as api_012
from hkmc_api_app import api_013_inspection_success_notification as api_013
from hkmc_api_app import api_014_monthly_inspection_info as api_014
from hkmc_api_app import api_015_paid_supplied_sales_status as api_015
from hkmc_api_app import api_016_jeonju_kanban_order_info as api_016
from hkmc_api_app import common
from hkmc_api_app.common import Api

APIS: tuple[Api, ...] = (
    api_001.API,
    api_002.API,
    api_003.API,
    api_004.API,
    api_005.API,
    api_006.API,
    api_007.API,
    api_008.API,
    api_009.API,
    api_010.API,
    api_011.API,
    api_012.API,
    api_013.API,
    api_014.API,
    api_015.API,
    api_016.API,
)

BY_INDEX = {api.index: api for api in APIS}

READABLE = tuple(api for api in APIS if not api.writes)


def for_company(company: str) -> tuple[Api, ...]:
    return tuple(api for api in READABLE if api.supports(company))


def for_indexes(indexes: Iterable[str], company: str) -> tuple[Api, ...]:
    chosen = set(indexes)
    return tuple(api for api in for_company(company) if api.index in chosen)


def ordered(indexes: Iterable[str]) -> tuple[Api, ...]:
    chosen = set(indexes)
    return tuple(api for api in READABLE if api.index in chosen)


SWEEP_PLANTS = {
    "005": lambda company: api_005.INVENTORY_PLANTS[company],
    "007": lambda company: tuple(common.PLANTS[company]),
}


def sweeps(api: Api) -> bool:
    return api.index in SWEEP_PLANTS


def plants_for(api: Api, company: str) -> tuple[str, ...]:
    return tuple(SWEEP_PLANTS[api.index](company))
