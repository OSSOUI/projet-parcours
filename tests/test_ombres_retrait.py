"""Retrait des ombres hors experimentation (plan de performances, etapes 1.2 a 1.4).

Aucun appel au modele : le modele est simule, ou les reponses enregistrees sont rejouees.

  1.3  les prompts des decisions REELLES sont identiques, octet par octet, avec et sans
       ombres (modele simule, puis run reel demo_fumee rejoue) ; seuls des prompts
       d'ombre s'ajoutent, et le monde ne change pas.
  1.2  l'en-tete dit explicitement si un run a des ombres ; les analyses qui en ont
       besoin refusent un run sans ombres, ou disent qu'elles ne peuvent rien en tirer.
  1.4  un run sans ombres se rejoue : monde identique, scene egale au dernier releve,
       faits de la narratrice calculables, sans aucun fait d'ombre.

    python3 tests/test_ombres_retrait.py
"""
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

import emergence  # noqa: E402
import experience_memoire  # noqa: E402
import rejeu_integration  # noqa: E402
import simuler  # noqa: E402
from ephemere import narration as N  # noqa: E402
from ephemere import population  # noqa: E402
from ephemere.agents_llm import DecideurLLM  # noqa: E402
from ephemere.contrat import SENS  # noqa: E402
from ephemere.horloge import Horloge  # noqa: E402
from ephemere.journal import Journal  # noqa: E402
from ephemere.llm import extraire_json  # noqa: E402
from ephemere.monde import Monde  # noqa: E402
from ephemere.rag import Base  # noqa: E402
from ephemere.regles_v1 import Regles  # noqa: E402

echecs = []
OMBRES_E = ["sans_discours", "sans_social", "sans_souvenirs"]
OMBRES_A = ["sans_discours", "sans_social"]
DEMO = os.path.join(RACINE, "runs", "demo_fumee.jsonl")


def verifier(nom, condition, detail=""):
    print(f"  {'ok   ' if condition else 'ECHEC'} {nom}" + ("" if condition else f" {detail}"))
    if not condition:
        echecs.append(nom)


class Simule:
    """Modele simule : la reponse ne depend que de la cle de l'appel (agent, instant),
    comme la graine du vrai client. Une ombre recoit donc la meme reponse que la
    decision reelle, et le monde ne depend pas du nombre d'ombres."""

    graine = 0

    def __init__(self):
        self.appels, self.derniere_mesure, self.dernier_brut = [], {}, None

    def json(self, systeme, consigne, taille="llm_petit", cle=None, **_):
        self.appels.append((cle, systeme + "\n\0" + consigne))
        self.derniere_mesure = {"latence_s": 0.0}
        h = int(hashlib.sha256(cle.encode()).hexdigest()[:8], 16)
        r = {"porte": h % 2 == 0, "categorie": list(SENS)[h % 6], "sens": f"sens {h % 7}",
             "publication": f"message {h % 97}" if h % 3 == 0 else "", "destinataire": "",
             "raison": f"motif {h % 13}"}
        self.dernier_brut = json.dumps(r)
        return r


class Rejoue(Simule):
    """Rend la reponse brute enregistree du run (perception.v1), a la decision comme aux ombres."""

    def __init__(self, reponses):
        super().__init__()
        self.reponses = reponses

    def json(self, systeme, consigne, taille="llm_petit", cle=None, **_):
        self.appels.append((cle, systeme + "\n\0" + consigne))
        self.derniere_mesure = {"latence_s": 0.0}
        _, agent, t = cle.split(":")
        self.dernier_brut = self.reponses.get((agent, int(t)))
        return None if self.dernier_brut is None else extraire_json(self.dernier_brut)


def simuler_run(client, ombres, memoire_sens, graine=100, jours=6, tete=None):
    """La boucle du simulateur, modele remplace. Renvoie (evenements, appels)."""
    agents, config = population.construire(os.path.join(RACINE, "config", "tessaline.json"),
                                           20, graine)
    base = Base(os.path.join(RACINE, "corpus"))
    r = Regles()
    moteurs = {t: DecideurLLM(client, t, base=base, memoire_sens=memoire_sens)
               for t in ("llm_petit", "llm_grand")}
    decideurs = {a["id"]: moteurs.get(a["moteur"], r) for a in agents}
    args = types.SimpleNamespace(jours=jours, pas_min=1440, releve_min=1440, ombres=list(ombres),
                                 telemetrie=None, dialogue=None, pionnieres_simultanees=False)
    with tempfile.TemporaryDirectory() as d:
        with Journal(d, "essai", Horloge(0)) as j:
            entete = {"mode": "synchrone", "nb_agents": 20, "graine": graine, "jours": jours,
                      "config": "tessaline.json", "version_contrat": "1.10.0",
                      "modele_social": "v1", "corpus": "corpus", "graine_llm": True,
                      "sortie_structuree": False, "definitions": "courtes",
                      "conversation": {"par_jour": 0, "repliques": 3}, "temperature": 0.9,
                      "empreinte_prompt": "ceb1fc47a4f9", "modeles": None, **(tete or {}),
                      "ombres": list(ombres), "memoire_sens": memoire_sens}
            j.ecrire("run.v2", **entete)
            j.ecrire("population.v1", resume=population.resume(agents), agents=[
                {k: a[k] for k in ("id", "nom", "profil", "groupe", "moteur", "porte")}
                for a in agents])
            with contextlib.redirect_stdout(io.StringIO()):
                simuler.tourner_synchrone(Monde(agents, config.get("perception")), decideurs, j,
                                          j.horloge, args)
            chemin = j.chemin
        with open(chemin, encoding="utf-8") as f:
            evs = [json.loads(l) for l in f]
    return evs, client.appels


def prompts_reels(appels):
    """Le premier appel de chaque cle est la decision reelle ; les suivants sont ses ombres."""
    vus, reels = set(), []
    for cle, texte in appels:
        if cle not in vus:
            vus.add(cle)
            reels.append(texte)
    return reels


def empreinte(textes):
    return hashlib.sha256("\n\0\0".join(textes).encode()).hexdigest()


def ecrire(evs, dossier, nom):
    chemin = os.path.join(dossier, f"{nom}.jsonl")
    with open(chemin, "w", encoding="utf-8") as f:
        for e in evs:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return chemin


print("1.3 Les prompts des decisions reelles ne dependent pas des ombres (modele simule)")
sorties = {}
for memoire_sens in (False, True):
    for ombres in ([], OMBRES_A, OMBRES_E):
        evs, appels = simuler_run(Simule(), ombres, memoire_sens)
        sorties[(memoire_sens, tuple(ombres))] = (evs, appels)
    for ombres in (OMBRES_A, OMBRES_E):
        sans, avec = sorties[(memoire_sens, ())], sorties[(memoire_sens, tuple(ombres))]
        r0, r1 = prompts_reels(sans[1]), prompts_reels(avec[1])
        etiquette = f"{'E (--memoire-sens)' if memoire_sens else 'A'}, {len(ombres)} ombres"
        verifier(f"{etiquette} : {len(r1)} prompts reels identiques octet par octet a ceux sans "
                 f"ombres (sha {empreinte(r1)[:12]})", r0 == r1, (len(r0), len(r1)))
        verifier(f"{etiquette} : seuls des prompts d'ombre s'ajoutent "
                 f"({len(avec[1])} appels = {len(r1)} x {1 + len(ombres)})",
                 len(sans[1]) == len(r0) and len(avec[1]) == len(r1) * (1 + len(ombres)))
        verifier(f"{etiquette} : monde identique (evenements hors ombres et en-tete)",
                 rejeu_integration.monde_de(sans[0]) == rejeu_integration.monde_de(avec[0]))
        verifier(f"{etiquette} : {sum(e['schema'] == 'ombre.v1' for e in avec[0])} evenements "
                 "ombre.v1, aucun sans ombres",
                 not any(e["schema"] == "ombre.v1" for e in sans[0])
                 and sum(e["schema"] == "ombre.v1" for e in avec[0]) == len(r1) * len(ombres))

print("\n1.3 bis Le meme controle sur un run reel enregistre (demo_fumee, rejoue sans modele)")
if os.path.exists(DEMO):
    with open(DEMO, encoding="utf-8") as f:
        demo = [json.loads(l) for l in f]
    reponses = {(e["agent"], e["t_sim"]): e["reponse_brute"]
                for e in demo if e["schema"] == "perception.v1"}
    tete = demo[0]
    rejeux = {}
    for ombres in ([], OMBRES_E):
        rejeux[tuple(ombres)] = simuler_run(Rejoue(reponses), ombres, True, graine=tete["graine"],
                                            jours=tete["jours"])
    r0, r1 = prompts_reels(rejeux[()][1]), prompts_reels(rejeux[tuple(OMBRES_E)][1])
    verifier(f"demo_fumee : {len(r1)} prompts reels identiques avec 3 ombres et sans ombres",
             r0 == r1 and len(r0) == len(reponses))
    verifier("demo_fumee rejoue AVEC ses 3 ombres : monde identique au journal enregistre",
             rejeu_integration.monde_de(rejeux[tuple(OMBRES_E)][0]) == rejeu_integration.monde_de(demo))
    verifier("demo_fumee rejoue SANS ombres : meme monde, sans aucun ombre.v1",
             rejeu_integration.monde_de(rejeux[()][0]) == rejeu_integration.monde_de(demo)
             and not any(e["schema"] == "ombre.v1" for e in rejeux[()][0]))
else:
    verifier("runs/demo_fumee.jsonl present", False)

print("\n1.2 Metadonnees explicites, et analyses qui refusent ou le disent")
sans_e = sorties[(True, ())][0]
avec_e = sorties[(True, tuple(OMBRES_E))][0]
verifier("en-tete d'un run sans ombres : champ ombres present et vide",
         "ombres" in sans_e[0] and sans_e[0]["ombres"] == [])
verifier("en-tete d'un run avec ombres : la liste des masques", avec_e[0]["ombres"] == OMBRES_E)
import demo_integration  # noqa: E402
o = demo_integration.ombres_du_run(sans_e)
verifier("rapport de demonstration : 'mesure du social impossible' et avertissement",
         o["mesure_du_social_possible"] is False and "jamais verser" in o["avertissement"])
with tempfile.TemporaryDirectory() as d:
    c_sans = ecrire(sans_e, d, "essai_sans_ombres")
    c_avec = ecrire(avec_e, d, "essai_avec_ombres")
    for condition in ("A", "E"):
        ctrl = experience_memoire.controler(c_sans, condition, 100)
        verifier(f"experience memoire : un run sans ombres est NON recevable en {condition} "
                 f"(ecart : {[e for e in ctrl['ecarts'] if 'ombres' in e]})",
                 not ctrl["recevable"] and any(e.startswith("ombres") for e in ctrl["ecarts"]))
    dist = emergence.distributions()
    with contextlib.redirect_stdout(io.StringIO()):
        em_sans = emergence.analyser(c_sans, dist, 50)
        em_avec = emergence.analyser(c_avec, dist, 50)
    verifier("emergence.py sur un run sans ombres : aucun temoin asservi calcule "
             "(seul le controle analytique, et il l'affiche)",
             em_sans["ombres"] == {} and set(em_avec["ombres"]) == set(OMBRES_E))
    sortie = io.StringIO()
    with contextlib.redirect_stdout(sortie):
        emergence.afficher(em_sans)
    verifier("emergence.py le dit en clair", "pas d'ombres dans ce run" in sortie.getvalue())

print("\n1.4 Rejeu d'un run sans ombres (demo_fumee rejoue sans ombres, sans modele)")
if os.path.exists(DEMO):
    with tempfile.TemporaryDirectory() as d:
        derive = rejeux[()][0]
        derive[0] = {**derive[0], **{k: tete[k] for k in ("config", "corpus") if k in tete}}
        # La boucle tourner_synchrone s'arrete au dernier releve : c'est simuler.py (main)
        # qui ecrit ensuite la fin du run. On reprend celle du run enregistre, apres
        # controle : meme run, les trois derniers evenements, contigus, apres le dernier releve.
        fin = demo[-3:]
        dernier_releve = max(e["t_sim"] for e in demo if e["schema"] == "indicateurs.v1")
        verifier("fin du run enregistre : energie.v1, coherence.v1, bilan.v1, dans cet ordre",
                 [e["schema"] for e in fin] == ["energie.v1", "coherence.v1", "bilan.v1"])
        verifier("fin du run enregistre : meme run, seq contigus et derniers du journal",
                 all(e["run"] == tete["run"] for e in fin)
                 and [e["seq"] for e in fin] == [len(demo) - 3, len(demo) - 2, len(demo) - 1])
        verifier("fin du run enregistre : posterieure ou egale au dernier releve, "
                 "et le journal derive s'arrete bien sur ce releve",
                 all(e["t_sim"] >= dernier_releve for e in fin)
                 and derive[-1]["schema"] == "indicateurs.v1"
                 and derive[-1]["t_sim"] == dernier_releve)
        derive = derive + [{**e, "seq": len(derive) + i} for i, e in enumerate(fin)]
        chemin = ecrire([{**e, "run": "demo_fumee_sans_ombres"} for e in derive], d,
                        "demo_fumee_sans_ombres")
        verifier("journal derive : seq continus de 0 a la fin",
                 [e["seq"] for e in derive] == list(range(len(derive))))
        evs = rejeu_integration.lire(chemin)
        m = rejeu_integration.rejouer_monde(evs)
        verifier(f"monde rejoue identique ({m.get('evenements_du_monde')} evenements), "
                 f"0 ombre", m.get("monde_identique") and m["ombres_journal"] == 0, m)
        s = rejeu_integration.rejouer_scene(evs)
        verifier(f"scene reconstruite egale au dernier releve ({s['adoption_scene']:.0%})",
                 s["identique_au_dernier_releve"] and s["manquants"] == 0)
        with contextlib.redirect_stdout(io.StringIO()):
            em = emergence.analyser(chemin, emergence.distributions(), 50)
        natures = []
        for fen, av, ap, e in N.parcourir(evs, 1, em):
            table, _ = N.faits(fen, av, ap, e)
            natures += [f.get("nature") for f in table.values()]
        verifier(f"faits de la narratrice calculables ({len(natures)} faits), aucun fait d'ombre, "
                 "indicateur d'emergence present",
                 natures and "ombre" not in natures and "emergence" in natures)

print()
if echecs:
    print(f"{len(echecs)} verification(s) en echec.")
    sys.exit(1)
print("Toutes les verifications passent.")
