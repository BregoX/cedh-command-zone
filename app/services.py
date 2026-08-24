import random
from collections import Counter
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from .models import Event, Pod, Registration, Round, Seat

def standings(event: Event):
    wins = Counter(p.winner_id for r in event.rounds for p in r.pods if p.winner_id)
    return sorted(((r.player, wins[r.player_id]) for r in event.registrations), key=lambda x: (-x[1], x[0].name))

def create_round(db: Session, event: Event) -> Round:
    history = Counter()
    for rnd in event.rounds:
        for pod in rnd.pods:
            ids = [s.player_id for s in pod.seats]
            for a in ids:
                for b in ids:
                    if a < b: history[a, b] += 1
    ids = [r.player_id for r in event.registrations]
    random.shuffle(ids)
    ordered=[]
    while ids:
        if not ordered: ordered.append(ids.pop()); continue
        podmates=ordered[-(len(ordered)%4):] if len(ordered)%4 else []
        best=min(ids,key=lambda x:sum(history[min(x,y),max(x,y)] for y in podmates))
        ids.remove(best);ordered.append(best)
    rnd=Round(event_id=event.id,number=len(event.rounds)+1)
    for i in range(0,len(ordered),4):
        pod=Pod(table_number=i//4+1)
        pod.seats=[Seat(player_id=pid,position=n+1) for n,pid in enumerate(ordered[i:i+4])]
        rnd.pods.append(pod)
    db.add(rnd);db.commit();return rnd

def load_event(db: Session, event_id: int | None = None):
    q=select(Event).options(selectinload(Event.registrations).selectinload(Registration.player),selectinload(Event.rounds).selectinload(Round.pods).selectinload(Pod.seats).selectinload(Seat.player)).order_by(Event.id.desc())
    if event_id:q=q.where(Event.id==event_id)
    return db.scalars(q).first()
