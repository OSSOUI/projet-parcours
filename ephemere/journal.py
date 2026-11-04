"""Journal d'un run : evenements valides d'un cote, rejets de l'autre (F3, F4).

Deux fichiers par run, et c'est volontaire :
  runs/<run>.jsonl         les evenements conformes au contrat
  runs/<run>.rejets.jsonl  ceux qui ne le sont pas, avec la raison

Le fichier reste la reference : c'est lui qui permet le rejeu sans appel
LLM (E3). Kafka s'y branche (bus.py) : il recoit les memes evenements.

Chaque evenement conforme porte seq (contrat 1.9.0) : son rang parmi les
evenements conformes du run, 0 pour l'en-tete. Un evenement rejete n'en
consomme pas, si bien que seq vaut le numero de ligne du fichier et qu'un
trou dans les seq recus par un consommateur est une perte, pas un rejet.
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
            "seq": self.nb_ecrits,
            "t_sim": self.horloge.minutes,
            "t_sim_lisible": self.horloge.lisible(),
            "t_emission": datetime.now().isoformat(timespec="milliseconds"),
            "t_traitement": None,
            **corps,
        }
        ok, raison = contrat.verifier(evt)
        if ok and schema in contrat.SCHEMAS_OBSERVATEUR:
            # Le journal du monde est ce que le monde peut relire ; la
            # narratrice n'y entre pas (elle a son fichier, narratrice.py).
            ok, raison = False, f"{schema} : evenement d'observateur hors du journal du monde"
        if not ok:
            del evt["seq"]
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
            # Bilan du producteur, que verifier_kafka.py confronte au topic (C1).
            bilan = self.bus.fermer()
            with open(self.chemin[:-len(".jsonl")] + ".kafka.json", "w", encoding="utf-8") as f:
                json.dump({**bilan, "ecrits": self.nb_ecrits}, f, ensure_ascii=False, indent=1)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.fermer()


class JournalIllisible(ValueError):
    pass


def lire(chemin):
    """Les evenements d'un run, chacun avec son seq, anciens runs compris.

    Avant le contrat 1.9.0, les evenements n'avaient pas de seq. Le journal
    etait alors aussi le seul ecrivain du fichier, ouvert en "w", une ligne par
    evenement conforme, dans l'ordre d'ecriture : le numero de ligne (a partir
    de 0) est donc ce seq. On ne le suppose pas, on le verifie : un seul run
    par fichier, l'en-tete en premiere ligne, aucune ligne vide ou illisible,
    et un temps simule qui ne recule jamais. Sinon JournalIllisible, plutot
    qu'un identifiant faux. Un seq present doit valoir le numero de ligne.
    Verifie le 4 novembre 2026 sur les 120 journaux de runs/ : tous passent.
    """
    evenements, runs, t_prec = [], set(), None
    with open(chemin, encoding="utf-8") as f:
        for i, ligne in enumerate(f):
            try:
                e = json.loads(ligne)
            except ValueError:
                raise JournalIllisible(f"{chemin}:{i + 1} : ligne illisible")
            if i == 0 and e.get("schema") not in contrat.SCHEMAS_RUN:
                raise JournalIllisible(f"{chemin} : pas d'en-tete de run en tete")
            if e.get("seq", i) != i:
                raise JournalIllisible(f"{chemin}:{i + 1} : seq {e['seq']} au lieu de {i}")
            if t_prec is not None and e["t_sim"] < t_prec:
                raise JournalIllisible(f"{chemin}:{i + 1} : le temps simule recule")
            t_prec = e["t_sim"]
            runs.add(e.get("run"))
            e.setdefault("seq", i)
            evenements.append(e)
    if len(runs) > 1:
        raise JournalIllisible(f"{chemin} : plusieurs runs dans un fichier {sorted(runs)}")
    return evenements


def identifiant(evt):
    """L'identifiant d'un evenement, cite par la narratrice et l'analyse."""
    return f"{evt['run']}#{evt['seq']}"
