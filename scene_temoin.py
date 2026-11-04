"""Scene temoin : un client WebSocket qui recoit du pont exactement ce que recoit Godot.

Ce n'est PAS Godot. Il sert a mesurer la chaine quand Godot ne peut pas tourner
sans ecran ou sans intervention : il se (re)connecte comme main.gd (toutes les
2 s), note chaque message comme la trace EPHEMERE_TRACE de main.gd, et applique
la meme regle d'affichage du recit : constats seuls, hypotheses et incertitudes
masquees.

    .venv/bin/python scene_temoin.py runs/demo_x.scene_temoin.jsonl
"""
import asyncio
import json
import signal
import sys
import time

URL = "ws://localhost:8765"


async def ecouter(chemin):
    import websockets
    narrations, etat = {}, {}
    with open(chemin, "w", encoding="utf-8") as trace:
        def noter(**x):
            trace.write(json.dumps({"ms": round(time.monotonic() * 1000), **x},
                                   ensure_ascii=False) + "\n")
            trace.flush()
        try:
            while True:
                try:
                    async with websockets.connect(URL, max_size=None) as ws:
                        noter(type="connexion")
                        async for brut in ws:
                            lu = json.loads(brut)
                            if lu.get("type") == "narration":
                                n = lu["narration"]
                                narrations[n["narration"]] = n
                                noter(type="narration", run=etat.get("run"),
                                      narration=n["narration"], t_sim=n["t_sim"],
                                      constats=len(n["constats"]),
                                      hypotheses=len(n["hypotheses"]),
                                      incertitudes=len(n["incertitudes"]))
                                continue
                            if lu.get("type") == "accuse":
                                continue
                            etat = lu.get("etat", lu)
                            for n in etat.get("narrations", []):
                                narrations[n["narration"]] = n
                            e = lu.get("evenement", {})
                            noter(type="evenement" if "evenement" in lu else "etat",
                                  run=etat.get("run"), seq=e.get("seq"), schema=e.get("schema"),
                                  vus=etat.get("indicateurs", {}).get("evenements_vus", 0),
                                  narrations=len(narrations))
                except (OSError, Exception) as e:
                    if isinstance(e, asyncio.CancelledError):
                        raise
                    noter(type="deconnexion", raison=type(e).__name__)
                    await asyncio.sleep(2.0)
        finally:
            # Ce que le panneau "Recit" afficherait a la fin : les constats seuls.
            affiche = [{"narration": k, "constats": [c["texte"] for c in n["constats"]],
                        "masquees": len(n["hypotheses"]) + len(n["incertitudes"])}
                       for k, n in sorted(narrations.items(), key=lambda x: x[1]["t_sim"])]
            noter(type="fin", run=etat.get("run"),
                  indicateurs=etat.get("indicateurs"), recit_affiche=affiche)


def main():
    boucle = asyncio.new_event_loop()
    tache = boucle.create_task(ecouter(sys.argv[1]))
    for s in (signal.SIGTERM, signal.SIGINT):
        boucle.add_signal_handler(s, tache.cancel)
    try:
        boucle.run_until_complete(tache)
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    main()
