"""Synthetic commerce adapter: configurable scenarios, never a live search."""
from datetime import datetime,timedelta
from app.vi_adapter import sign_offer


def offers_for(approved):
    f=approved['fields'];domain=approved['domain']
    offers=[]
    for kind in ('match','mismatch'):
        o={'id':approved['id']+'-'+kind,'domain':domain,'currency':'USD','total_cents':29500 if kind=='match' else 28000,'scenario':kind,'cabin':'economy','refundable':False,'title':'Direct route' if kind=='match' else 'Lower price, three connections'}
        if domain=='flight':
            origin=(f.get('origin_airports') or ['EWR'])[0];dest=(f.get('destination_airports') or ['MCO'])[0];day=f.get('departure_date') or '2026-11-12'
            airports=[origin,dest] if kind=='match' else [origin,'ATL','CLT','TPA',dest]
            # Synthetic fixed offset is disclosed, not asserted as real airport timezone data.
            start=datetime.fromisoformat(day+'T09:00:00-05:00')
            segments=[]
            for i in range(len(airports)-1):
                dep=start+timedelta(hours=i*3);arr=dep+timedelta(hours=2)
                segments.append({'origin':airports[i],'destination':airports[i+1],'departure':dep.isoformat(),'arrival':arr.isoformat()})
            o.update(segments=segments,route_complete=True,technical_stops=0,trip_type='one_way')
        elif domain=='hotel':
            o['max_adults']=2
            o.update(city=f.get('city') or 'Orlando',checkin_date=f.get('checkin_date') or '2026-11-12',checkout_date=f.get('checkout_date') or '2026-11-14',rooms=1,breakfast=kind=='match',refundable=kind=='match',accessible=kind=='match',title='Breakfast & cancellation included' if kind=='match' else 'Room only, nonrefundable')
        else: o['title']='Synthetic product offer'
        offers.append({'id':o['id'],'checkout_jwt':sign_offer(o)})
    return offers
