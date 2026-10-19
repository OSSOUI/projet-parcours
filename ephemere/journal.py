"""Journal d'un run : evenements valides d'un cote, rejets de l'autre (F3, F4).

Deux fichiers par run, et c'est volontaire :
  runs/<run>.jsonl         les evenements conformes au contrat
  runs/<run>.rejets.jsonl  ceux qui ne le sont pas, avec la raison

Le fichier reste la reference : c'est lui qui permet le rejeu sans appel
LLM (E3). Kafka viendra s'y brancher a l'etape 4, sans rien changer ici.
"""
import json
import os
from datetime import datetime

from . import contrat


class Journal:
    def __init__(self, dossier, nom_run, horloge, bus=None):
        os.makedirs(dossier, exist_ok=True)
        self.nom_run = nom_run
        self.horloge = horloge
        self.chemin = os.path.join(dossier, f"{nom_run}.jsonl")
        self.chemin_rejets = os.path.join(dossier, f"{nom_run}.rejets.jsonl")
        self._f = open(self.chemin, "w", encoding="utf-8")
        self._r = None
        self.bus = bus          # publication Kafka, facultative (exigence C1)
        self.nb_ecrits = 0
        self.nb_rejets = 0

    def ecrire(self, schema, **corps):
        """Enveloppe, verifie puis enregistre un evenement. Ne leve jamais."""
        evt = {
            "schema": schema,
            "run": self.nom_run,
            "t_sim": self.horloge.minutes,
            "t_sim_lisible": self.horloge.lisible(),
            "t_emission": datetime.now().isoformat(timespec="milliseconds"),
            "t_traitement": None,
            **corps,
        }
        ok, raison = contrat.verifier(evt)
        if not ok:
            self._rejeter(evt, raison)
            return None
        self._f.write(json.dumps(evt, ensure_ascii=False) + "\n")
        self._f.flush()
        self.nb_ecrits += 1
        # Seuls les evenements conformes partent dans Kafka : un consommateur
        # n'a pas a re-valider ce que le producteur a deja refuse.
        if self.bus:
            self.bus.publier(evt)
        return evt

    def _rejeter(self, evt, raison):
        if self._r is None:
            self._r = open(self.chemin_rejets, "w", encoding="utf-8")
        self._r.write(json.dumps({"raison": raison, "evenement": evt},
                                 ensure_ascii=False) + "\n")
        self._r.flush()
        self.nb_rejets += 1
        if self.nb_rejets == 1:
            print(f"  [evenement non conforme isole : {raison}]")

    def fermer(self):
        self._f.close()
        if self._r:
            self._r.close()
        if self.bus:
            self.bus.fermer()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.fermer()
