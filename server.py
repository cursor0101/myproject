import os
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Local modules
from db import (
    init_db as init_kri_db,
    seed_from_json as seed_kri,
    fetch_all_data as fetch_all_kri,
    get_kri,
    add_system as db_add_system,
    upsert_data_point as kri_upsert_data_point,
    update_data_point as kri_update_data_point,
    delete_data_point as kri_delete_data_point,
    delete_system as db_delete_system,
    VALUE_FIELD_MAP as KRI_VALUE_FIELD_MAP,
    APP_BASED_KRIS,
)

from rhi_db import (
    init_db as init_rhi_db,
    seed_from_json as seed_rhi,
    fetch_all_data as fetch_all_rhi,
    get_rhi,
    upsert_data_point as rhi_upsert_data_point,
    update_data_point as rhi_update_data_point,
    delete_data_point as rhi_delete_data_point,
    upsert_duration_point as rhi_upsert_duration_point,
    update_duration_point as rhi_update_duration_point,
    upsert_ratio_point as rhi_upsert_ratio_point,
    update_ratio_point as rhi_update_ratio_point,
    RHI_VALUE_FIELD_MAP,
    RATIO_RHIS,
)

from mitredb import (
    init_db as init_mitre_db,
    save_dataset as mitre_save_dataset,
    get_latest_dataset as mitre_get_latest,
)

from riskanalysisdb import (
    init_db as init_risk_db,
    save_dataset as risk_save_dataset,
    get_latest_dataset as risk_get_latest,
    set_latest_range as risk_set_latest_range,
)

import ipaddress
import socket


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KRI_FILE = os.path.join(BASE_DIR, 'kri.html')
RHI_FILE = os.path.join(BASE_DIR, 'rhi.html')
MITRE_FILE = os.path.join(BASE_DIR, 'mitre.html')
RISK_ANALYSIS_FILE = os.path.join(BASE_DIR, 'risk_analysis.html')


# KRI metadata for reporting
KRI_METADATA: Dict[str, Dict[str, str]] = {
    'kri2': {
        'name': 'KRI2',
        'definition': 'Percentage of critical initiatives/projects engage with information security at the requirements phase',
        'threshold': '95%',
    },
    'kri3': {
        'name': 'KRI3',
        'definition': 'Percentage of environments evaluated to determine whether or not they are critical',
        'threshold': '80%',
    },
    'kri4': {
        'name': 'KRI4',
        'definition': 'Number of realized risk which is coming from threats that identified as weak threat with low probability',
        'threshold': '1 realized risk',
    },
    'kri5': {
        'name': 'KRI5',
        'definition': 'Percentage of outstanding Critical risk mitigation actions vs. agreed plan',
        'threshold': '0% for Critical Risks',
    },
    'kri6': {
        'name': 'KRI6',
        'definition': 'Percentage of outstanding High and moderate risk mitigation actions vs. agreed plan',
        'threshold': '10%',
    },
    'kri8': {
        'name': 'KRI8',
        'definition': 'Mean Time Between Critical System Failures (Days)',
        'threshold': '120 days',
    },
    'kri9': {
        'name': 'KRI9',
        'definition': 'Unauthorized access to strictly confidential data in any critical systems',
        'threshold': '0 unauthorized accesses',
    },
    'kri10': {
        'name': 'KRI10',
        'definition': 'Number of incidents affecting critical applications',
        'threshold': '2 incidents per month',
    },
    'kri12': {
        'name': 'KRI12',
        'definition': 'Incidents Exceeding RTO',
        'threshold': '0',
    },
    'kri13': {
        'name': 'KRI13',
        'definition': 'Number of incidents resulting in downtime within RTO',
        'threshold': '2 (lower is better)',
    },
    'kri15': {
        'name': 'KRI15',
        'definition': '% of Critical Systems without up to date patches',
        'threshold': '0%',
    },
    'kri18': {
        'name': 'KRI18',
        'definition': 'Percentage of critical systems not included in business continuity and disaster recovery plans',
        'threshold': '10%',
    },
    'kri19': {
        'name': 'KRI19',
        'definition': 'Average time to recover from an incident',
        'threshold': '< RTO time (BCP)',
    },
    'kri20': {
        'name': 'KRI20',
        'definition': 'Number of incidents resulting in loss of customer information',
        'threshold': '0 incidents per month',
    },
    'kri21': {
        'name': 'KRI21',
        'definition': 'Number of privacy incidents resulting in legal/regulatory proceedings',
        'threshold': '0 incidents per month',
    },
    'kri22': {
        'name': 'KRI22',
        'definition': 'Percentage of incidents detected by controls',
        'threshold': '70%',
    },
    'kri27': {
        'name': 'KRI27',
        'definition': 'Percentage of Critical risks defined in risk registry which do not have a defined risk owner and approved action plan',
        'threshold': '0% for Critical Risks',
    },
    'kri28': {
        'name': 'KRI28',
        'definition': 'Percentage of High or Moderate risks defined in risk registry which do not have a defined risk owner and approved action plan',
        'threshold': '10% for High/Moderate',
    },
}


# ---------------- Pydantic models (KRI) ----------------
class AddSystemRequest(BaseModel):
    kriId: str
    systemName: str


class AddDataPointRequest(BaseModel):
    kriId: str
    period: str
    value: float
    valueField: Optional[str] = None
    systemName: Optional[str] = None


class UpdateDataPointRequest(BaseModel):
    kriId: str
    period: str
    systemName: Optional[str] = None
    value: Optional[float] = None
    valueField: Optional[str] = None


class DeleteDataPointRequest(BaseModel):
    kriId: str
    period: str
    systemName: Optional[str] = None


class DeleteSystemRequest(BaseModel):
    kriId: str
    systemName: str


# ---------------- Pydantic models (RHI) ----------------
class RHIAddDataPointRequest(BaseModel):
    rhiId: str
    period: str
    value: Optional[float] = None
    hours: Optional[int] = None
    minutes: Optional[int] = None
    seconds: Optional[int] = None
    numerator: Optional[int] = None
    denominator: Optional[int] = None


class RHIUpdateDataPointRequest(BaseModel):
    rhiId: str
    period: str
    value: Optional[float] = None
    hours: Optional[int] = None
    minutes: Optional[int] = None
    seconds: Optional[int] = None
    numerator: Optional[int] = None
    denominator: Optional[int] = None


class RHIDeleteDataPointRequest(BaseModel):
    rhiId: str
    period: str


# ---------------- Pydantic models (MITRE) ----------------
class MitreUploadRequest(BaseModel):
    filename: Optional[str] = None
    chartData: List[Dict[str, Any]]
    allParametersData: List[Dict[str, Any]]


# ---------------- Pydantic models (Risk Analysis) ----------------
class RiskUploadRequest(BaseModel):
    filename: Optional[str] = None
    fromDate: str
    toDate: str
    columnAData: Dict[str, int]
    columnRData: Dict[str, int]
    risksRows: List[List[Any]]
    fileB64: Optional[str] = None


class RiskSetRangeRequest(BaseModel):
    fromDate: str
    toDate: str


app = FastAPI()


# CORS (relaxed for simplicity; tighten in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------- ACCESS CONTROL (IP whitelist) ----------------
_ALLOWED_EDIT_IPS_ENV = os.environ.get('ALLOWED_EDIT_IPS', '10.124.8.116,10.124.8.115,192.168.100.16')
ALLOWED_EDIT_NETWORKS = []
for part in _ALLOWED_EDIT_IPS_ENV.split(','):
	part = part.strip()
	if not part:
		continue
	try:
		ALLOWED_EDIT_NETWORKS.append(ipaddress.ip_network(part, strict=False))
	except Exception:
		# Ignore malformed entries
		pass

# Collects best-effort list of local interface IPs (IPv4/IPv6) without external deps
def _get_local_ip_addresses() -> List[str]:
	ips = set()
	try:
		hostname = socket.gethostname()
		for info in socket.getaddrinfo(hostname, None):
			ip = info[4][0]
			if ip:
				ips.add(ip)
	except Exception:
		pass
	# Always include loopbacks for completeness
	ips.update({'127.0.0.1', '::1'})
	return list(ips)

def _extract_client_ip(request: Request) -> str:
	xfwd = request.headers.get('x-forwarded-for') or request.headers.get('X-Forwarded-For')
	if xfwd:
		# Take the first IP in the list
		return xfwd.split(',')[0].strip()
	xreal = request.headers.get('x-real-ip') or request.headers.get('X-Real-IP')
	if xreal:
		return xreal.strip()
	client = getattr(request, 'client', None)
	return getattr(client, 'host', '') or ''

def is_ip_whitelisted(ip_str: str) -> bool:
	if not ALLOWED_EDIT_NETWORKS:
		return False
	# If request comes from loopback, allow when a whitelisted IP/network belongs to this host
	if ip_str in ('127.0.0.1', '::1'):
		try:
			for local_ip in _get_local_ip_addresses():
				try:
					local_addr = ipaddress.ip_address(local_ip)
					for net in ALLOWED_EDIT_NETWORKS:
						if local_addr in net:
							return True
				except Exception:
					continue
		except Exception:
			pass
	try:
		ip = ipaddress.ip_address(ip_str)
	except Exception:
		return False
	for net in ALLOWED_EDIT_NETWORKS:
		if ip in net:
			return True
	return False

async def require_edit_access(request: Request) -> None:
	ip = _extract_client_ip(request)
	if not is_ip_whitelisted(ip):
		raise HTTPException(status_code=403, detail='Editing is not allowed from your IP')

# Public endpoint to let clients know if they can edit
@app.get('/api/access')
async def api_access(request: Request):
	ip = _extract_client_ip(request)
	return { 'ip': ip, 'canEdit': is_ip_whitelisted(ip) }


@app.on_event('startup')
async def startup_event():
    # Initialize DBs
    init_kri_db(drop=False)
    init_rhi_db(drop=False)
    init_mitre_db(drop=False)
    init_risk_db(drop=False)

    # Seed if empty
    kri_data = fetch_all_kri()
    if all((not v.get('data')) and (not v.get('applications')) for v in kri_data.values()):
        seed_kri()

    rhi_data = fetch_all_rhi()
    if all((not v.get('data')) for v in rhi_data.values()):
        seed_rhi()


@app.get('/')
async def root_redirect():
    return RedirectResponse(url='/kri', status_code=307)


@app.get('/kri', response_class=HTMLResponse)
async def get_kri_index():
    if not os.path.exists(KRI_FILE):
        raise HTTPException(status_code=404, detail='kri.html not found')
    with open(KRI_FILE, 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read(), status_code=200)


@app.get('/rhi', response_class=HTMLResponse)
async def get_rhi_index():
    if not os.path.exists(RHI_FILE):
        raise HTTPException(status_code=404, detail='rhi.html not found')
    with open(RHI_FILE, 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read(), status_code=200)


@app.get('/mitre', response_class=HTMLResponse)
async def get_mitre_index():
    if not os.path.exists(MITRE_FILE):
        raise HTTPException(status_code=404, detail='mitre.html not found')
    with open(MITRE_FILE, 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read(), status_code=200)


@app.get('/risk-analysis', response_class=HTMLResponse)
async def get_risk_analysis_index():
    if not os.path.exists(RISK_ANALYSIS_FILE):
        raise HTTPException(status_code=404, detail='risk_analysis.html not found')
    with open(RISK_ANALYSIS_FILE, 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read(), status_code=200)


@app.get('/api/health')
async def health():
    return {'status': 'ok'}


# ----------- KRI API -----------

@app.get('/api/kri-data')
async def api_get_kri_data():
    return fetch_all_kri()


@app.get('/api/kri/item/{kri_id}')
async def api_get_single_kri(kri_id: str):
    if kri_id not in KRI_VALUE_FIELD_MAP:
        raise HTTPException(status_code=400, detail='Unknown KRI id')
    return get_kri(kri_id)


@app.post('/api/add-system')
async def api_add_system(req: AddSystemRequest, _: None = Depends(require_edit_access)):
    kri = req.kriId
    if kri not in KRI_VALUE_FIELD_MAP:
        raise HTTPException(status_code=400, detail='Unknown KRI id')
    if kri not in APP_BASED_KRIS:
        raise HTTPException(status_code=400, detail='KRI is not applications-based')
    name = req.systemName.strip()
    if not name:
        raise HTTPException(status_code=400, detail='System name is required')
    db_add_system(kri, name)
    return {'success': True, 'kriId': kri, 'kri': get_kri(kri)}


@app.post('/api/add-data-point')
async def api_add_data_point(req: AddDataPointRequest, _: None = Depends(require_edit_access)):
    kri = req.kriId
    if kri not in KRI_VALUE_FIELD_MAP:
        raise HTTPException(status_code=400, detail='Unknown KRI id')

    field = req.valueField or KRI_VALUE_FIELD_MAP[kri]
    if field != KRI_VALUE_FIELD_MAP[kri]:
        raise HTTPException(status_code=400, detail=f'Invalid valueField for {kri}. Expected {KRI_VALUE_FIELD_MAP[kri]}')

    period = req.period.strip()
    if not period:
        raise HTTPException(status_code=400, detail='Period is required')

    value = float(req.value)
    if value < 0:
        raise HTTPException(status_code=400, detail='Value must be non-negative')

    if kri in APP_BASED_KRIS and not req.systemName:
        raise HTTPException(status_code=400, detail='systemName is required for applications-based KRI')

    kri_upsert_data_point(kri, period, value, system_name=req.systemName)
    return {'success': True, 'kriId': kri, 'kri': get_kri(kri)}


@app.put('/api/update-data-point')
async def api_update_data_point(req: UpdateDataPointRequest, _: None = Depends(require_edit_access)):
    kri = req.kriId
    if kri not in KRI_VALUE_FIELD_MAP:
        raise HTTPException(status_code=400, detail='Unknown KRI id')
    if req.valueField and req.valueField != KRI_VALUE_FIELD_MAP[kri]:
        raise HTTPException(status_code=400, detail=f'Invalid valueField for {kri}. Expected {KRI_VALUE_FIELD_MAP[kri]}')

    changed = kri_update_data_point(
        kri_id=kri,
        period=req.period,
        value=req.value,
        system_name=req.systemName,
    )
    if changed == 0:
        raise HTTPException(status_code=404, detail='Data point not found or no changes provided')
    return {'success': True, 'kriId': kri, 'kri': get_kri(kri)}


@app.delete('/api/delete-data-point')
async def api_delete_data_point(req: DeleteDataPointRequest, _: None = Depends(require_edit_access)):
    kri = req.kriId
    if kri not in KRI_VALUE_FIELD_MAP:
        raise HTTPException(status_code=400, detail='Unknown KRI id')
    deleted = kri_delete_data_point(kri, req.period, req.systemName)
    if deleted == 0:
        raise HTTPException(status_code=404, detail='Data point not found')
    return {'success': True, 'kriId': kri, 'kri': get_kri(kri)}


@app.delete('/api/delete-system')
async def api_delete_system(req: DeleteSystemRequest, _: None = Depends(require_edit_access)):
    kri = req.kriId
    if kri not in KRI_VALUE_FIELD_MAP:
        raise HTTPException(status_code=400, detail='Unknown KRI id')
    if kri not in APP_BASED_KRIS:
        raise HTTPException(status_code=400, detail='KRI is not applications-based')
    pts, sys = db_delete_system(kri, req.systemName)
    if sys == 0:
        raise HTTPException(status_code=404, detail='System not found')
    return {'success': True, 'deletedPoints': pts, 'deletedSystems': sys, 'kriId': kri, 'kri': get_kri(kri)}


# ----------- RHI API -----------

@app.get('/api/rhi-data')
async def api_get_rhi_data():
    return fetch_all_rhi()


@app.get('/api/rhi/item/{rhi_id}')
async def api_get_single_rhi(rhi_id: str):
    if rhi_id not in RHI_VALUE_FIELD_MAP:
        raise HTTPException(status_code=400, detail='Unknown RHI id')
    return get_rhi(rhi_id)


@app.post('/api/rhi/add-data-point')
async def api_rhi_add_data_point(req: RHIAddDataPointRequest, _: None = Depends(require_edit_access)):
    rhi = req.rhiId
    if rhi not in RHI_VALUE_FIELD_MAP:
        raise HTTPException(status_code=400, detail='Unknown RHI id')
    period = req.period.strip()
    if not period:
        raise HTTPException(status_code=400, detail='Period is required')

    if rhi == 'rhi107':
        hours = int(req.hours or 0)
        minutes = int(req.minutes or 0)
        seconds = int(req.seconds or 0)
        if hours < 0 or minutes < 0 or seconds < 0:
            raise HTTPException(status_code=400, detail='Hours/Minutes/Seconds must be non-negative')
        rhi_upsert_duration_point(rhi, period, hours, minutes, seconds)
    elif rhi in RATIO_RHIS:
        if req.numerator is None or req.denominator is None:
            raise HTTPException(status_code=400, detail='numerator and denominator are required')
        numerator = int(req.numerator)
        denominator = int(req.denominator)
        if numerator < 0 or denominator <= 0:
            raise HTTPException(status_code=400, detail='Invalid numerator/denominator')
        rhi_upsert_ratio_point(rhi, period, numerator, denominator)
    else:
        if req.value is None:
            raise HTTPException(status_code=400, detail='Value is required')
        value = float(req.value)
        if value < 0:
            raise HTTPException(status_code=400, detail='Value must be non-negative')
        rhi_upsert_data_point(rhi, period, value)

    return {'success': True, 'rhiId': rhi, 'rhi': get_rhi(rhi)}


@app.put('/api/rhi/update-data-point')
async def api_rhi_update_data_point(req: RHIUpdateDataPointRequest, _: None = Depends(require_edit_access)):
    rhi = req.rhiId
    if rhi not in RHI_VALUE_FIELD_MAP:
        raise HTTPException(status_code=400, detail='Unknown RHI id')

    if rhi == 'rhi107':
        hours = req.hours
        minutes = req.minutes
        seconds = req.seconds
        if hours is None and minutes is None and seconds is None:
            raise HTTPException(status_code=400, detail='Provide at least one of hours/minutes/seconds')
        for x in [hours, minutes, seconds]:
            if x is not None and int(x) < 0:
                raise HTTPException(status_code=400, detail='Hours/Minutes/Seconds must be non-negative')
        changed = rhi_update_duration_point(rhi_id=rhi, period=req.period, hours=hours, minutes=minutes, seconds=seconds)
    elif rhi in RATIO_RHIS:
        num = req.numerator
        den = req.denominator
        if num is None and den is None:
            raise HTTPException(status_code=400, detail='Provide numerator and/or denominator')
        if num is not None and num < 0:
            raise HTTPException(status_code=400, detail='Invalid numerator')
        if den is not None and den <= 0:
            raise HTTPException(status_code=400, detail='Invalid denominator')
        changed = rhi_update_ratio_point(rhi_id=rhi, period=req.period, numerator=num, denominator=den)
    else:
        changed = rhi_update_data_point(rhi_id=rhi, period=req.period, value=req.value)

    if changed == 0:
        raise HTTPException(status_code=404, detail='Data point not found or no changes provided')
    return {'success': True, 'rhiId': rhi, 'rhi': get_rhi(rhi)}


@app.delete('/api/rhi/delete-data-point')
async def api_rhi_delete_data_point(req: RHIDeleteDataPointRequest, _: None = Depends(require_edit_access)):
    rhi = req.rhiId
    if rhi not in RHI_VALUE_FIELD_MAP:
        raise HTTPException(status_code=400, detail='Unknown RHI id')
    deleted = rhi_delete_data_point(rhi, req.period)
    if deleted == 0:
        raise HTTPException(status_code=404, detail='Data point not found')
    return {'success': True, 'rhiId': rhi, 'rhi': get_rhi(rhi)}


# ----------- MITRE API (DB-backed, no localStorage) -----------

@app.get('/api/mitre/latest')
async def api_mitre_latest():
    ds = mitre_get_latest()
    if not ds:
        return {'exists': False}
    return {'exists': True, 'dataset': ds}


@app.post('/api/mitre/upload')
async def api_mitre_upload(req: MitreUploadRequest, _: None = Depends(require_edit_access)):
    filename = (req.filename or '').strip() or f'upload_{datetime.utcnow().isoformat()}'
    mitre_save_dataset(filename=filename, chart_data=req.chartData, all_parameters_data=req.allParametersData)
    ds = mitre_get_latest()
    return {'success': True, 'dataset': ds}


# ----------- Risk Analysis API (DB-backed, no localStorage) -----------

@app.get('/api/risk/latest')
async def api_risk_latest():
    ds = risk_get_latest()
    if not ds:
        return {'exists': False}
    return {'exists': True, 'dataset': ds}


@app.post('/api/risk/upload')
async def api_risk_upload(req: RiskUploadRequest, _: None = Depends(require_edit_access)):
    filename = (req.filename or '').strip() or f'upload_{datetime.utcnow().isoformat()}'
    risk_save_dataset(
        filename=filename,
        from_date=req.fromDate,
        to_date=req.toDate,
        column_a_counts=req.columnAData,
        column_r_counts=req.columnRData,
        risks_rows=req.risksRows,
        file_b64=req.fileB64,
    )
    ds = risk_get_latest()
    return {'success': True, 'dataset': ds}


@app.post('/api/risk/set-range')
async def api_risk_set_range(req: RiskSetRangeRequest):
    # no edit required to change view preference
    risk_set_latest_range(req.fromDate, req.toDate)
    return {'success': True}


# ---------------------- REPORT HELPERS ----------------------

def months_for_quarter(q: str) -> List[str]:
    mapping = {
        'Q1': ['01', '02', '03'],
        'Q2': ['04', '05', '06'],
        'Q3': ['07', '08', '09'],
        'Q4': ['10', '11', '12'],
    }
    return mapping.get(q, [])


def filter_kri_dataset_by_year_quarter(dataset: Dict[str, Any], year: Optional[str], quarter: Optional[str]) -> Dict[str, Any]:
    """Filter by year+quarter when both provided; if only year provided, filter by year; otherwise return dataset as-is."""
    if not year and not quarter:
        return dataset

    result: Dict[str, Any] = {}
    months = months_for_quarter(quarter) if quarter else []
    for kri_id, content in dataset.items():
        if 'applications' in content and content['applications'] is not None:
            apps: Dict[str, List[Dict[str, Any]]] = {}
            for sys_name, points in (content['applications'] or {}).items():
                filtered: List[Dict[str, Any]] = []
                for p in points:
                    period = str(p.get('period', ''))
                    if '-' not in period:
                        continue
                    if period.startswith('Q'):
                        # Qx-YYYY
                        if period.endswith(year) and period.split('-')[0] == quarter:
                            filtered.append(p)
                    else:
                        # MM-YYYY (kri10)
                        mm, yy = period.split('-')
                        if yy == year and mm in months:
                            filtered.append(p)
                if filtered:
                    apps[sys_name] = filtered
            result[kri_id] = {'applications': apps}
        else:
            rows: List[Dict[str, Any]] = []
            for p in (content.get('data') or []):
                period = str(p.get('period', ''))
                if '-' not in period:
                    continue
                if period.startswith('Q'):
                    if year and quarter:
                        if period.endswith(year) and period.split('-')[0] == quarter:
                            rows.append(p)
                    elif year:
                        if period.endswith(year):
                            rows.append(p)
                else:
                    # assume MM-YYYY (e.g., kri10)
                    mm, yy = period.split('-')
                    if year and quarter:
                        if yy == year and mm in months:
                            rows.append(p)
                    elif year:
                        if yy == year:
                            rows.append(p)
            result[kri_id] = {'data': rows}
    return result


def filter_rhi_dataset_by_year_quarter(dataset: Dict[str, Any], year: Optional[str], quarter: Optional[str]) -> Dict[str, Any]:
    """Filter by year+quarter when both provided; if only year provided, filter by year; otherwise return dataset as-is."""
    if not year and not quarter:
        return dataset

    result: Dict[str, Any] = {}
    months = months_for_quarter(quarter) if quarter else []
    quarterly_ids = {'rhi100', 'rhi101', 'rhi110', 'rhi121', 'rhi158'}
    yearly_ids = {'rhi105', 'rhi108'}
    for rhi_id, content in dataset.items():
        rows: List[Dict[str, Any]] = []
        for p in (content.get('data') or []):
            period = str(p.get('period', ''))
            if rhi_id in quarterly_ids:
                if year and quarter:
                    if period.endswith(year) and period.split('-')[0] == quarter:
                        rows.append(p)
                elif year:
                    if period.endswith(year):
                        rows.append(p)
            elif rhi_id in yearly_ids:
                if year:
                    if period == year:
                        rows.append(p)
            else:
                # monthly MM-YYYY
                if '-' in period and not period.startswith('Q'):
                    mm, yy = period.split('-')
                    if year and quarter:
                        if yy == year and mm in months:
                            rows.append(p)
                    elif year:
                        if yy == year:
                            rows.append(p)
        result[rhi_id] = {'data': rows}
    return result


def kri_report_html(filtered: Dict[str, Any], year: Optional[str], quarter: Optional[str]) -> str:
    def esc(s: str) -> str:
        return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    def fmt_number(val: Any) -> str:
        try:
            # allow ints to render without trailing .0, keep non-integer floats as-is
            num = float(val)
            if num.is_integer():
                return str(int(num))
            # avoid excessive precision changes; keep original if string had formatting
            return str(val)
        except Exception:
            return str(val)

    title_suffix = f" - {esc(quarter)} {esc(year)}" if (year and quarter) else " - All Data"
    html_parts: List[str] = [
        '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>KRI Report</title>',
        '<style>body{font-family:Arial, sans-serif;padding:20px;} h1{color:#333;} h2{color:#667eea;} table{border-collapse:collapse;width:100%;margin-bottom:24px;} th,td{border:1px solid #ddd;padding:8px;} th{background:#f5f7ff;text-align:left;} .meta{margin:4px 0 12px 0;color:#555;} .sys{font-weight:bold;margin-top:8px;} .kri-card{border:1px solid #e5e7ff;padding:16px;border-radius:8px;margin-bottom:16px;background:#fbfcff;}</style>',
        '</head><body>',
        f'<h1>KRI Report{title_suffix}</h1>'
    ]
    for kri_id in sorted(filtered.keys()):
        meta = KRI_METADATA.get(kri_id, {'name': kri_id.upper(), 'definition': '', 'threshold': ''})
        content = filtered[kri_id]
        html_parts.append('<div class="kri-card">')
        display_name = meta.get('name') or kri_id.upper()
        if str(display_name).upper() == kri_id.upper():
            header_text = esc(str(display_name))
        else:
            header_text = f"{esc(str(display_name))} ({esc(kri_id.upper())})"
        html_parts.append(f'<h2>{header_text}</h2>')
        if meta.get('definition'):
            html_parts.append(f'<div class="meta"><b>Definition:</b> {esc(meta["definition"])}</div>')
        if meta.get('threshold'):
            html_parts.append(f'<div class="meta"><b>Threshold:</b> {esc(meta["threshold"])}</div>')
        if 'applications' in content and content['applications']:
            # applications-based
            html_parts.append('<table><thead><tr><th>System</th><th>Period</th><th>Value</th></tr></thead><tbody>')
            for sys_name, pts in content['applications'].items():
                for p in pts:
                    period = str(p.get('period', ''))
                    # figure out value field
                    value = None
                    for key in ['value', 'incidents', 'percentage', 'count']:
                        if key in p:
                            value = p[key]
                            break
                    html_parts.append(f'<tr><td>{esc(sys_name)}</td><td>{esc(period)}</td><td>{esc(fmt_number(value))}</td></tr>')
            html_parts.append('</tbody></table>')
        else:
            # simple data
            rows = content.get('data') or []
            html_parts.append('<table><thead><tr><th>Period</th><th>Value</th></tr></thead><tbody>')
            for p in rows:
                period = str(p.get('period', ''))
                value = None
                for key in ['value', 'percentage', 'count']:
                    if key in p:
                        value = p[key]
                        break
                html_parts.append(f'<tr><td>{esc(period)}</td><td>{esc(fmt_number(value))}</td></tr>')
            html_parts.append('</tbody></table>')
        html_parts.append('</div>')
    html_parts.append('</body></html>')
    return ''.join(html_parts)


def rhi_report_html(filtered: Dict[str, Any], year: Optional[str], quarter: Optional[str]) -> str:
    def esc(s: str) -> str:
        return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    def fmt_number(val: Any) -> str:
        try:
            num = float(val)
            if num.is_integer():
                return str(int(num))
            return str(val)
        except Exception:
            return str(val)

    title_suffix = f" - {esc(quarter)} {esc(year)}" if (year and quarter) else " - All Data"
    html_parts: List[str] = [
        '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>RHI Report</title>',
        '<style>body{font-family:Arial, sans-serif;padding:20px;} h1{color:#333;} h2{color:#667eea;} table{border-collapse:collapse;width:100%;margin-bottom:24px;} th,td{border:1px solid #ddd;padding:8px;} th{background:#f5f7ff;text-align:left;} .rhi-card{border:1px solid #e5e7ff;padding:16px;border-radius:8px;margin-bottom:16px;background:#fbfcff;}</style>',
        '</head><body>',
        f'<h1>RHI Report{title_suffix}</h1>'
    ]
    for rhi_id in sorted(filtered.keys()):
        content = filtered[rhi_id]
        html_parts.append('<div class="rhi-card">')
        html_parts.append(f'<h2>{esc(rhi_id.upper())}</h2>')
        rows = content.get('data') or []
        html_parts.append('<table><thead><tr><th>Period</th><th>Value/Details</th></tr></thead><tbody>')
        for p in rows:
            period = str(p.get('period', ''))
            if rhi_id == 'rhi107':
                val = f'{int(p.get("hours",0)):02d}:{int(p.get("minutes",0)):02d}:{int(p.get("seconds",0)):02d}'
            elif rhi_id in RATIO_RHIS:
                # Keep percentage with one decimal, but clean integer-like parts
                numerator = fmt_number(p.get('numerator', 0))
                denominator = fmt_number(p.get('denominator', 0))
                perc_val = float(p.get('value', 0.0))
                val = f'{numerator}/{denominator} = {perc_val:.1f}%'
            else:
                val = fmt_number(p.get('value', ''))
            html_parts.append(f'<tr><td>{esc(period)}</td><td>{esc(val)}</td></tr>')
        html_parts.append('</tbody></table>')
        html_parts.append('</div>')
    html_parts.append('</body></html>')
    return ''.join(html_parts)


def respond_as_format(html: str, filename_stem: str, fmt: str) -> Response:
    fmt = (fmt or 'html').lower()

    if fmt == 'html':
        return Response(
            content=html,
            media_type='text/html; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename="{filename_stem}.html"'}
        )

    elif fmt == 'pdf':
        # Try WeasyPrint first (best fidelity)
        try:
            from weasyprint import HTML as WeasyHTML
            pdf_bytes = WeasyHTML(string=html, base_url=BASE_DIR).write_pdf()
            return Response(
                content=pdf_bytes,
                media_type='application/pdf',
                headers={'Content-Disposition': f'attachment; filename="{filename_stem}.pdf"'}
            )
        except Exception:
            # Fallback to xhtml2pdf if WeasyPrint is unavailable
            try:
                from io import BytesIO
                from xhtml2pdf import pisa
                pdf_io = BytesIO()
                # xhtml2pdf expects utf-8 input, writes to a file-like object
                pisa_status = pisa.CreatePDF(src=html, dest=pdf_io, encoding='utf-8')
                if getattr(pisa_status, 'err', 0):
                    raise RuntimeError('xhtml2pdf failed to generate PDF')
                pdf_io.seek(0)
                return StreamingResponse(
                    pdf_io,
                    media_type='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename="{filename_stem}.pdf"'}
                )
            except Exception as e2:
                # Explicit error so clients won’t save HTML when PDF was requested
                raise HTTPException(
                    status_code=500,
                    detail=f'PDF generation failed. Install one of the PDF backends: weasyprint or xhtml2pdf. Error: {e2}'
                )

    elif fmt == 'docx':
        try:
            from docx import Document
            from docx.shared import Pt
            try:
                from bs4 import BeautifulSoup as BS
                soup = BS(html, 'html.parser')
            except Exception:
                soup = None
            doc = Document()
            style = doc.styles['Normal']
            style.font.name = 'Arial'
            style.font.size = Pt(10)

            def add_table_from_html(table_el):
                rows = table_el.find_all('tr')
                if not rows:
                    return False
                header_cells = rows[0].find_all(['th','td'])
                table = doc.add_table(rows=1, cols=len(header_cells))
                hdr_cells = table.rows[0].cells
                for i, c in enumerate(header_cells):
                    hdr_cells[i].text = c.get_text(' ', strip=True)
                for r in rows[1:]:
                    tds = r.find_all(['td','th'])
                    row_cells = table.add_row().cells
                    for i, c in enumerate(tds):
                        if i < len(row_cells):
                            row_cells[i].text = c.get_text(' ', strip=True)
                doc.add_paragraph('')
                return True

            content_added = False
            if soup:
                kri_cards = soup.select('div.kri-card')
                rhi_cards = soup.select('div.rhi-card')
                if kri_cards:
                    for card in kri_cards:
                        h2 = card.find('h2')
                        if h2:
                            doc.add_paragraph(h2.get_text(' ', strip=True))
                            content_added = True
                        meta_divs = card.find_all('div', class_='meta')
                        for m in meta_divs:
                            text = m.get_text(' ', strip=True)
                            if text:
                                doc.add_paragraph(text)
                                content_added = True
                        table_el = card.find('table')
                        if table_el:
                            if add_table_from_html(table_el):
                                content_added = True
                elif rhi_cards:
                    for card in rhi_cards:
                        h2 = card.find('h2')
                        if h2:
                            doc.add_paragraph(h2.get_text(' ', strip=True))
                            content_added = True
                        table_el = card.find('table')
                        if table_el:
                            if add_table_from_html(table_el):
                                content_added = True
                else:
                    body = soup.find('body') or soup
                    for el in body.descendants:
                        name = getattr(el, 'name', None)
                        if name in ['h1','h2','h3']:
                            txt = el.get_text(' ', strip=True)
                            if txt:
                                doc.add_paragraph(txt)
                                content_added = True
                        elif name == 'table':
                            if add_table_from_html(el):
                                content_added = True

            if not soup or not content_added:
                doc.add_paragraph('Report')
                doc.add_paragraph('Export produced no structured sections; raw HTML follows:')
                doc.add_paragraph(html)

            from io import BytesIO
            buf = BytesIO()
            doc.save(buf)
            buf.seek(0)
            return StreamingResponse(
                buf,
                media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                headers={'Content-Disposition': f'attachment; filename="{filename_stem}.docx"'}
            )
        except Exception as e:
            fallback = f'<!-- DOCX generation failed: {e} -->' + html
            return Response(
                content=fallback,
                media_type='text/html; charset=utf-8',
                headers={'Content-Disposition': f'attachment; filename="{filename_stem}.html"'}
            )
    else:
        raise HTTPException(status_code=400, detail='Unsupported format. Use html|pdf|docx')


# ---------------------- REPORT ENDPOINTS ----------------------

@app.get('/api/kri/report')
async def api_kri_report(year: Optional[str] = None, quarter: Optional[str] = None, format: Optional[str] = 'html'):
    quarter = (quarter or '').upper() or None
    dataset = fetch_all_kri()
    filtered = filter_kri_dataset_by_year_quarter(dataset, year, quarter)
    html = kri_report_html(filtered, year, quarter)
    fname = f'kri_report_{quarter or "ALL"}_{year or "ALL"}'
    return respond_as_format(html, fname, format or 'html')


@app.get('/api/rhi/report')
async def api_rhi_report(year: Optional[str] = None, quarter: Optional[str] = None, format: Optional[str] = 'html'):
    quarter = (quarter or '').upper() or None
    dataset = fetch_all_rhi()
    filtered = filter_rhi_dataset_by_year_quarter(dataset, year, quarter)
    html = rhi_report_html(filtered, year, quarter)
    fname = f'rhi_report_{quarter or "ALL"}_{year or "ALL"}'
    return respond_as_format(html, fname, format or 'html')