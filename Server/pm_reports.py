import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Query
from fastapi.responses import HTMLResponse, Response

CUR_MAP = {"ر.ي": "YER", "ي.ر": "YER", "ر.ي.": "YER", "ريال": "YER", "YR": "YER", "YER": "YER"}


def _cur(c):
    c = (c or "").strip()
    return CUR_MAP.get(c, c) or "-"


def _num(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def _ts(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


import re as _re


def _ts2(s, tzinfo):
    if not s:
        return None
    s = str(s).strip().replace("Z", "+00:00")
    s = _re.sub(r"(\.\d{6})\d+", r"\1", s)
    try:
        d = datetime.fromisoformat(s)
    except Exception:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=tzinfo)
    return d.astimezone(timezone.utc)


def _new():
    return {"count": 0, "sum": 0.0, "min": None, "max": None}


def _add(a, v):
    a["count"] += 1
    a["sum"] += v
    a["min"] = v if a["min"] is None else min(a["min"], v)
    a["max"] = v if a["max"] is None else max(a["max"], v)


def _out(a):
    n = a["count"]
    return {
        "count": n,
        "sum": round(a["sum"], 2),
        "avg": round(a["sum"] / n, 2) if n else 0,
        "min": a["min"] or 0,
        "max": a["max"] or 0,
    }


def build_summary(db_path, frm, to, tz, wallet, device):
    try:
        tzinfo = timezone(timedelta(hours=float(tz)))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid tz")
    now_local = datetime.now(tzinfo)
    try:
        if frm:
            start_l = datetime.fromisoformat(frm).replace(tzinfo=tzinfo)
        else:
            start_l = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        if to:
            end_l = datetime.fromisoformat(to).replace(tzinfo=tzinfo) + timedelta(minutes=1)
        else:
            end_l = now_local + timedelta(minutes=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid date")
    if end_l <= start_l:
        raise HTTPException(status_code=400, detail="end before start")
    start_u = start_l.astimezone(timezone.utc)
    end_u = end_l.astimezone(timezone.utc)

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT deviceId, walletName, transactionType, amount, currency, "
            "senderName, referenceNumber, receivedAt, smsTime FROM transactions"
        ).fetchall()
    finally:
        conn.close()

    all_wallets, all_devices = set(), set()
    t_tot, t_wal, t_type, t_day, t_dev = {}, {}, {}, {}, {}
    items = []

    for dev, wal, typ, amt, cur, snd, ref, rec, sms in rows:
        wal = wal or "-"
        dev = dev or "unknown"
        all_wallets.add(wal)
        all_devices.add(dev)
        ts = _ts2(sms, tzinfo) or _ts2(rec, tzinfo)
        if ts is None or ts < start_u or ts >= end_u:
            continue
        if wallet and wal != wallet:
            continue
        if device and dev != device:
            continue
        v = _num(amt)
        c = _cur(cur)
        typ = typ or "-"
        day = ts.astimezone(tzinfo).strftime("%Y-%m-%d")
        for store, key in (
            (t_tot, (c,)),
            (t_wal, (wal, c)),
            (t_type, (wal, typ, c)),
            (t_day, (day, wal, c)),
            (t_dev, (dev, c)),
        ):
            _add(store.setdefault(key, _new()), v)
        items.append((ts, {
            "time": ts.astimezone(tzinfo).strftime("%Y-%m-%d %H:%M"),
            "wallet": wal, "type": typ, "amount": v, "currency": c,
            "sender": snd or "", "ref": ref or "", "device": dev,
        }))

    items.sort(key=lambda x: x[0])

    def rows_of(store, names):
        out = []
        for key in sorted(store):
            d = dict(zip(names, key))
            d.update(_out(store[key]))
            out.append(d)
        return out

    return {
        "period": {
            "from": start_l.strftime("%Y-%m-%d %H:%M"),
            "to": (end_l - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"),
        },
        "count": len(items),
        "wallets": sorted(all_wallets),
        "devices": sorted(all_devices),
        "totals": rows_of(t_tot, ("currency",)),
        "by_wallet": rows_of(t_wal, ("wallet", "currency")),
        "by_type": rows_of(t_type, ("wallet", "type", "currency")),
        "daily": rows_of(t_day, ("date", "wallet", "currency")),
        "by_device": rows_of(t_dev, ("device", "currency")),
        "items": [i[1] for i in items],
    }


PAGE = r"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>تقارير PaymentMonitor</title>
<style>
body{font-family:Tahoma,"Segoe UI",Arial,sans-serif;margin:0;background:#f3f5f9;color:#1b2434}
.wrap{max-width:1100px;margin:0 auto;padding:16px}
.card{background:#fff;border-radius:10px;padding:14px 16px;margin-bottom:12px;border:1px solid #dde3ee}
.row{display:flex;flex-wrap:wrap;gap:10px;align-items:end}
label{font-size:12px;color:#5b6679;display:flex;flex-direction:column;gap:3px}
input,select{padding:7px 8px;border:1px solid #c5cddc;border-radius:6px;font:inherit}
button{padding:8px 14px;border:1px solid #1d3f7a;background:#1d3f7a;color:#fff;border-radius:6px;font:inherit;cursor:pointer}
button.alt{background:#fff;color:#1d3f7a}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:6px 8px;border-bottom:1px solid #e6eaf2;text-align:right}
th{background:#eef2f9}
h1{font-size:20px;margin:0 0 4px}
h2{font-size:15px;margin:0 0 8px}
.kpis{display:flex;flex-wrap:wrap;gap:10px}
.kpi{flex:1;min-width:160px;background:#eef2f9;border-radius:8px;padding:10px}
.kpi b{display:block;font-size:20px}
.muted{color:#5b6679;font-size:12px}
.sign{display:none}
@media print{body{background:#fff}.noprint{display:none!important}.card{border:none;padding:0;margin-bottom:14px;break-inside:avoid}.sign{display:flex;gap:40px;margin-top:24px}.wrap{max-width:none;padding:0}}
</style></head><body><div class="wrap">
<div class="card"><h1>تقرير المدفوعات</h1><div class="muted" id="period"></div>
<div class="sign"><span>اسم الكاشير: ____________</span><span>التوقيع: ____________</span><span>المستلم: ____________</span></div></div>
<div class="card noprint">
<div class="row">
<label>من تاريخ ووقت<input type="datetime-local" id="from"></label>
<label>إلى تاريخ ووقت<input type="datetime-local" id="to"></label>
<label>المحفظة<select id="wallet"><option value="">الكل</option></select></label>
<label>الهاتف<select id="device"><option value="">الكل</option></select></label>
<label>فرق التوقيت عن UTC<input type="number" id="tz" step="0.5" style="width:90px"></label>
</div>
<div class="row" style="margin-top:10px">
<button id="pToday" class="alt">اليوم</button>
<button id="pYest" class="alt">أمس</button>
<button id="pEve" class="alt">الوردية المسائية (20:00 - 08:00)</button>
<button id="pMorn" class="alt">الوردية الصباحية (08:00 - 20:00)</button>
<button id="pMonth" class="alt">الشهر الحالي</button>
</div>
<div class="row" style="margin-top:10px">
<button id="go">عرض التقرير</button>
<button id="prn" class="alt">طباعة</button>
<button id="csv" class="alt">تصدير Excel (CSV)</button>
<a href="/dashboard" class="muted">العودة إلى لوحة التحكم</a>
</div></div>
<div id="out"></div>
</div>
<script>
var DATA=null;
function $(i){return document.getElementById(i)}
function pad(n){return (n<10?'0':'')+n}
function li(d){return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+'T'+pad(d.getHours())+':'+pad(d.getMinutes())}
function fmt(n){return Number(n||0).toLocaleString('en-US',{maximumFractionDigits:2})}
function esc(s){return String(s==null?'':s).replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]})}
function at(h,m,addDays){var d=new Date();d.setDate(d.getDate()+addDays);d.setHours(h,m,0,0);return d}
function setRange(a,b){$('from').value=li(a);$('to').value=li(b)}
function fill(id,list){
 var sel=$(id),cur=sel.value;
 sel.innerHTML='<option value="">الكل</option>';
 list.forEach(function(x){
  var o=document.createElement('option');
  o.value=x;o.textContent=x.length>16?x.slice(0,16)+'...':x;
  sel.appendChild(o);
 });
 sel.value=cur;
}
function tbl(head,rows){
 var h='<table><thead><tr>';
 head.forEach(function(x){h+='<th>'+x+'</th>'});
 h+='</tr></thead><tbody>';
 rows.forEach(function(r){h+='<tr>';r.forEach(function(c){h+='<td>'+esc(c)+'</td>'});h+='</tr>'});
 if(!rows.length)h+='<tr><td colspan="'+head.length+'">لا توجد بيانات</td></tr>';
 return h+'</tbody></table>';
}
function sec(title,body){return '<div class="card"><h2>'+title+'</h2>'+body+'</div>'}
function render(d){
 $('period').textContent='من '+d.period.from+' إلى '+d.period.to+'  |  عدد العمليات: '+d.count;
 var k='<div class="kpis">';
 d.totals.forEach(function(t){
  k+='<div class="kpi"><span class="muted">إجمالي '+esc(t.currency)+'</span><b>'+fmt(t.sum)+'</b><span class="muted">'+t.count+' عملية، المتوسط '+fmt(t.avg)+'</span></div>';
 });
 if(!d.totals.length)k+='<div class="muted">لا توجد عمليات في هذه الفترة.</div>';
 k+='</div>';
 var h=sec('الملخص',k);
 h+=sec('حسب المحفظة',tbl(['المحفظة','العملة','العمليات','الإجمالي','المتوسط','الأقل','الأعلى'],
  d.by_wallet.map(function(r){return [r.wallet,r.currency,r.count,fmt(r.sum),fmt(r.avg),fmt(r.min),fmt(r.max)]})));
 h+=sec('حسب نوع العملية',tbl(['المحفظة','النوع','العملة','العمليات','الإجمالي'],
  d.by_type.map(function(r){return [r.wallet,r.type,r.currency,r.count,fmt(r.sum)]})));
 h+=sec('التقرير اليومي لكل محفظة',tbl(['التاريخ','المحفظة','العملة','العمليات','الإجمالي'],
  d.daily.map(function(r){return [r.date,r.wallet,r.currency,r.count,fmt(r.sum)]})));
 h+=sec('حسب الهاتف',tbl(['الهاتف','العملة','العمليات','الإجمالي'],
  d.by_device.map(function(r){return [r.device,r.currency,r.count,fmt(r.sum)]})));
 h+=sec('تفاصيل العمليات',tbl(['الوقت','المحفظة','النوع','المبلغ','العملة','المرسل','المرجع','الهاتف'],
  d.items.map(function(r){return [r.time,r.wallet,r.type,fmt(r.amount),r.currency,r.sender,r.ref,r.device.length>12?r.device.slice(0,12)+'...':r.device]})));
 $('out').innerHTML=h;
}
function run(){
 var q='from='+encodeURIComponent($('from').value)+'&to='+encodeURIComponent($('to').value)+
  '&tz='+encodeURIComponent($('tz').value)+'&wallet='+encodeURIComponent($('wallet').value)+
  '&device='+encodeURIComponent($('device').value);
 fetch('/api/reports/summary?'+q).then(function(r){
  if(!r.ok)return r.json().then(function(j){throw new Error(j.detail||r.status)});
  return r.json();
 }).then(function(d){DATA=d;fill('wallet',d.wallets);fill('device',d.devices);render(d)})
 .catch(function(e){$('out').innerHTML='<div class="card">تعذر تحميل التقرير: '+esc(e.message)+'</div>'});
}
function csv(){
 if(!DATA)return;
 var rows=[['الوقت','المحفظة','النوع','المبلغ','العملة','المرسل','المرجع','الهاتف']];
 DATA.items.forEach(function(i){rows.push([i.time,i.wallet,i.type,i.amount,i.currency,i.sender,i.ref,i.device])});
 var t=rows.map(function(r){return r.map(function(c){return '"'+String(c==null?'':c).replace(/"/g,'""')+'"'}).join(',')}).join('\r\n');
 var b=new Blob(['\ufeff'+t],{type:'text/csv;charset=utf-8'});
 var a=document.createElement('a');
 a.href=URL.createObjectURL(b);a.download='report.csv';
 document.body.appendChild(a);a.click();a.remove();
}
$('tz').value=-new Date().getTimezoneOffset()/60;
$('pToday').onclick=function(){setRange(at(0,0,0),at(23,59,0));run()};
$('pYest').onclick=function(){setRange(at(0,0,-1),at(23,59,-1));run()};
$('pEve').onclick=function(){
 if(new Date().getHours()>=20)setRange(at(20,0,0),at(7,59,1));else setRange(at(20,0,-1),at(7,59,0));
 run();
};
$('pMorn').onclick=function(){setRange(at(8,0,0),at(19,59,0));run()};
$('pMonth').onclick=function(){var s=at(0,0,0);s.setDate(1);setRange(s,at(23,59,0));run()};
$('go').onclick=run;
$('prn').onclick=function(){window.print()};
$('csv').onclick=csv;
if(location.search.indexOf('preset=shift')>=0){var h=new Date().getHours();if(h>=20)setRange(at(20,0,0),at(7,59,1));else if(h<8)setRange(at(20,0,-1),at(7,59,0));else setRange(at(8,0,0),at(19,59,0))}else setRange(at(0,0,0),at(23,59,0));
run();
</script></body></html>
"""


BTN = r"""<script>
(function(){
var WORD='\u0625\u0639\u062f\u0627\u062f\u0627\u062a';
var LABEL='\u0627\u0644\u062a\u0642\u0627\u0631\u064a\u0631';
var ICON='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><rect x="7" y="12" width="3" height="6"/><rect x="12" y="8" width="3" height="10"/><rect x="17" y="5" width="3" height="13"/></svg>';
var GRAD='linear-gradient(135deg,#16a34a,#0f766e)';
function norm(s){return (s||'').replace(/[^\u0600-\u06FF]/g,'')}
function findRef(){
 var els=document.querySelectorAll('button,a,[role="button"]');
 for(var i=0;i<els.length;i++){
  var e=els[i];
  if(e.id==='pm-reports-btn'||e.id==='pm-reports-fab')continue;
  if(norm(e.textContent)===WORD&&e.offsetParent!==null)return e;
 }
 return null;
}
function place(){
 if(document.getElementById('pm-reports-btn'))return true;
 var ref=findRef();
 if(!ref||!ref.parentNode)return false;
 var nb=ref.cloneNode(false);
 Array.prototype.slice.call(nb.attributes).forEach(function(a){
  if(a.name==='id'||a.name==='onclick'||a.name==='href'||a.name==='target'||a.name==='title'||a.name.indexOf('data-')===0||a.name.indexOf('aria-')===0)nb.removeAttribute(a.name);
 });
 nb.id='pm-reports-btn';
 if(nb.tagName==='A'){nb.setAttribute('href','/reports')}else{nb.setAttribute('type','button')}
 nb.innerHTML=ICON+'<span>'+LABEL+'</span>';
 nb.style.cssText=(ref.getAttribute('style')||'')+';display:inline-flex;align-items:center;gap:8px;background:'+GRAD+';color:#fff;border:2px solid #bbf7d0;font-weight:700;box-shadow:0 4px 12px rgba(22,163,74,.55);cursor:pointer';
 nb.addEventListener('click',function(ev){ev.preventDefault();ev.stopPropagation();window.location.href='/reports'});
 ref.parentNode.insertBefore(nb,ref.nextSibling);
 var f=document.getElementById('pm-reports-fab');
 if(f)f.remove();
 return true;
}
function fab(){
 if(document.getElementById('pm-reports-fab')||document.getElementById('pm-reports-btn')||!document.body)return;
 var a=document.createElement('a');
 a.id='pm-reports-fab';
 a.href='/reports';
 a.innerHTML=ICON+'<span>'+LABEL+'</span>';
 a.style.cssText='position:fixed;top:14px;left:14px;z-index:99999;display:inline-flex;align-items:center;gap:8px;padding:10px 18px;border-radius:10px;background:'+GRAD+';color:#fff;font:700 15px Tahoma,Arial,sans-serif;text-decoration:none;box-shadow:0 4px 12px rgba(0,0,0,.45)';
 document.body.appendChild(a);
}
document.addEventListener('click',function(ev){var t=ev.target&&ev.target.closest?ev.target.closest('button,a,[role="button"]'):null;if(t&&t.id!=='pm-reports-btn'&&norm(t.textContent)==='\u062a\u0642\u0631\u064a\u0631\u0627\u0644\u0648\u0631\u062f\u064a\u0629'){ev.preventDefault();ev.stopPropagation();window.location.href='/reports?preset=shift'}},true);
var n=0;
setInterval(function(){n++;if(!place()&&n>=6)fab()},700);
place();
})();
</script>"""


async def _inject(request, call_next):
    resp = await call_next(request)
    try:
        if request.url.path not in ("/dashboard", "/"):
            return resp
        if "text/html" not in resp.headers.get("content-type", ""):
            return resp
    except Exception:
        return resp
    body = b""
    async for chunk in resp.body_iterator:
        body += chunk
    headers = {k: v for k, v in resp.headers.items() if k.lower() not in ("content-length", "content-type")}
    try:
        html = body.decode("utf-8")
        if "pm-reports-btn" not in html:
            if _re.search(r"<body[^>]*>", html):
                html = _re.sub(r"<body[^>]*>", lambda m: m.group(0) + BTN, html, count=1)
            else:
                html += BTN
        body = html.encode("utf-8")
    except Exception:
        pass
    return Response(content=body, status_code=resp.status_code, headers=headers, media_type="text/html")


def register_reports(app, db_path):
    def summary(
        frm: Optional[str] = Query(default=None, alias="from"),
        to: Optional[str] = None,
        tz: float = 3.0,
        wallet: str = "",
        device: str = "",
    ):
        return build_summary(db_path, frm, to, tz, wallet, device)

    def page():
        return HTMLResponse(PAGE)

    app.add_api_route("/api/reports/summary", summary, methods=["GET"])
    app.add_api_route("/reports", page, methods=["GET"], include_in_schema=False)
    app.middleware("http")(_inject)
    print("[REPORTS] loaded: /reports")