"""Narratrice externe : separation, contrat, validation, erreurs, rejeu sans modele.
Aucun appel reseau : le modele est simule.

    python3 tests/test_narratrice.py
"""
import ast
import json
import os
import subprocess
import sys
import tempfile
import types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

import simuler  # noqa: E402
from ephemere import contrat, journal, population  # noqa: E402
from ephemere import narration as N  # noqa: E402
from ephemere.agents_llm import DecideurLLM  # noqa: E402
from ephemere.horloge import Horloge  # noqa: E402
from ephemere.monde import Monde  # noqa: E402
from ephemere.rag import Base  # noqa: E402
from ephemere.regles_v1 import Regles  # noqa: E402

echecs = []
MARQUEUR = "MARQUEUR_NARRATRICE_7731"


def verifier(nom, condition, detail=""):
    if condition:
        print(f"  ok   {nom}")
    else:
        print(f"  ECHEC {nom} {detail}")
        echecs.append(nom)


def graphe_imports(depart):
    """Fichiers du depot atteints depuis `depart` par import, a toute profondeur
    (imports dans les fonctions compris)."""
    vus, pile = set(), [os.path.join(RACINE, depart)]
    while pile:
        f = pile.pop()
        if f in vus or not os.path.exists(f):
            continue
        vus.add(f)
        paquet = os.path.dirname(f)
        for n in ast.walk(ast.parse(open(f, encoding="utf-8").read())):
            noms = []
            if isinstance(n, ast.Import):
                noms = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                if n.level:   # from . import x  /  from .x import y
                    base = paquet
                    noms = [os.path.relpath(os.path.join(base, (n.module or "")), RACINE)
                            .replace(os.sep, ".")]
                    if not n.module:
                        noms = [f"{noms[0]}.{a.name}" for a in n.names]
                else:
                    noms = [n.module] + [f"{n.module}.{a.name}" for a in n.names]
            for m in noms:
                chemin = os.path.join(RACINE, *m.split("."))
                pile += [chemin + ".py", os.path.join(chemin, "__init__.py")]
    return {os.path.relpath(f, RACINE) for f in vus}


class ClientFactice:
    """Modele simule : garde chaque consigne, rend la reponse donnee."""

    def __init__(self, reponse=None, erreur=None):
        self.reponse, self.erreur = reponse, erreur
        self.consignes = []
        self.derniere_mesure = {}
        self.dernier_brut = None
        self.temperature = 0.3

    def json(self, systeme, consigne, taille="llm_petit", **_):
        self.consignes.append(systeme + "\n" + consigne)
        self.derniere_mesure = {"taille": taille, "modele": "factice", "latence_s": 0.1,
                                "essais": 1, "graine": 1}
        if self.erreur:
            raise self.erreur
        r = self.reponse(consigne) if callable(self.reponse) else self.reponse
        self.dernier_brut = json.dumps(r) if r is not None else None
        return r


def run_regles(dossier, nom, jours=3, decideurs=None, base=None):
    """Un vrai run du simulateur (boucle synchrone), dans un dossier temporaire."""
    agents, config = population.construire(os.path.join(RACINE, "config", "tessaline.json"),
                                           20, 100)
    monde = Monde(agents, config.get("perception"))
    if decideurs is None:
        r = Regles()
        decideurs = {a["id"]: r for a in agents}
    else:
        decideurs = decideurs(agents)
    h = Horloge(0)
    args = types.SimpleNamespace(jours=jours, pas_min=1440, releve_min=1440, ombres=[],
                                 telemetrie=None, dialogue=None, pionnieres_simultanees=False)
    with journal.Journal(dossier, nom, h) as j:
        j.ecrire("run.v2", mode="synchrone", nb_agents=20, graine=100, jours=jours,
                 config="tessaline.json", version_contrat=contrat.VERSION_CONTRAT,
                 modele_social="v1")
        j.ecrire("population.v1", agents=[{k: a[k] for k in ("id", "nom", "profil", "groupe",
                                                             "moteur", "porte")} for a in agents],
                 resume={})
        simuler.tourner_synchrone(monde, decideurs, j, h, args)
        j.ecrire("bilan.v1", appels=0, tokens_entree=0, tokens_sortie=0, duree_run_s=0.0,
                 interrompu=False, incidents=0, par_taille={})
        return j.chemin


print("1. Separation : le simulateur ne peut ni importer ni lire la narratrice")
graphe = graphe_imports("simuler.py")
verifier(f"graphe d'imports de simuler.py calcule ({len(graphe)} fichiers)",
         "ephemere/agents_llm.py" in graphe and "ephemere/rag.py" in graphe)
verifier("ni ephemere/narration.py ni narratrice.py n'y figurent",
         "ephemere/narration.py" not in graphe and "narratrice.py" not in graphe)
interdits = (".narration.jsonl", "ephemere.narration", "import narration", "narratrice import",
             "lire_narrations")
# contrat.py definit les schemas de tous les evenements, observateur compris :
# il peut les nommer, mais il ne lit ni n'ecrit aucun fichier.
fautifs = [f for f in graphe if f != "ephemere/contrat.py"
           and any(x in open(os.path.join(RACINE, f), encoding="utf-8").read() for x in interdits)]
verifier("aucun fichier du simulateur ne nomme le fichier ou le module de narration",
         not fautifs, fautifs)
verifier("contrat.py ne fait aucune entree-sortie",
         "open(" not in open(os.path.join(RACINE, "ephemere", "contrat.py"), encoding="utf-8").read())
cote_agents = ("simuler.py", "ephemere/agents_llm.py", "ephemere/monde.py", "ephemere/rag.py",
               "ephemere/dialogue.py", "ephemere/regles_v1.py", "ephemere/population.py")
verifier("le code qui construit les prompts ne mentionne pas la narratrice",
         not [f for f in cote_agents
              if "narrat" in open(os.path.join(RACINE, f), encoding="utf-8").read().lower()])

print("\n2. Le journal du monde refuse les evenements d'observateur")
with tempfile.TemporaryDirectory() as d:
    with journal.Journal(d, "r", Horloge(0)) as j:
        j.ecrire("narratrice.v1", source="x", empreinte_source=None, mode="post", periode=1,
                 taille="llm_grand", modele="m", temperature=0.3, empreinte_prompt="e",
                 version_contrat="1")
        refuse = j.nb_ecrits == 0 and j.nb_rejets == 1
    verifier("narratrice.v1 refuse par Journal", refuse)
for chemin, attendu in (("corpus/x.narration.jsonl", "corpus"),
                        ("config/x.narration.jsonl", "config"),
                        ("runs/x.jsonl", "narration.jsonl")):
    try:
        N.Sortie(os.path.join(RACINE, chemin), "x", os.path.join(RACINE, "runs", "autre.jsonl"))
        verifier(f"sortie refusee : {chemin}", False)
    except ValueError as e:
        verifier(f"sortie refusee : {chemin}", attendu in str(e), str(e))
try:
    N.Sortie(os.path.join(RACINE, "runs", "x.narration.jsonl"), "x",
             os.path.join(RACINE, "runs", "x.narration.jsonl"))
    verifier("sortie refusee : le journal observe lui-meme", False)
except ValueError:
    verifier("sortie refusee : le journal observe lui-meme", True)

print("\n3. Un vrai run LLM (modele simule) : la narration n'entre dans aucun prompt")
REPONSE = {"porte": True, "categorie": "tendance", "sens": "c'est le moment",
           "publication": "je le porte aujourd'hui", "destinataire": "", "raison": "envie"}
with tempfile.TemporaryDirectory() as d:
    # Une narration piege, posee la ou elle serait si elle avait deja ete ecrite.
    for nom in ("piege.narration.jsonl", "piege.jsonl.narration.jsonl"):
        with open(os.path.join(d, nom), "w", encoding="utf-8") as f:
            f.write(json.dumps({"schema": "narration.v1", "texte": MARQUEUR}) + "\n")
    client = ClientFactice(REPONSE)
    base = Base(os.path.join(RACINE, "corpus"))

    def decideurs(agents):
        r = Regles()
        return {a["id"]: DecideurLLM(client, a["moteur"], base=base) if a["moteur"] != "regles"
                else r for a in agents}
    chemin = run_regles(d, "piege", jours=3, decideurs=decideurs)
    contenu = open(chemin, encoding="utf-8").read()
    verifier(f"{len(client.consignes)} prompts d'agents construits", len(client.consignes) > 10)
    verifier("le marqueur n'apparait dans aucun prompt",
             not any(MARQUEUR in c for c in client.consignes))
    verifier("ni dans le journal du monde (perceptions, memoires, documents)",
             MARQUEUR not in contenu)
    verifier("le corpus des agents ne lit rien dans le dossier des runs",
             all(not dd.passage.count(MARQUEUR) for dd in base.documents))
    verifier("le run n'a cree aucun fichier de narration",
             sorted(f for f in os.listdir(d) if "narration" in f)
             == ["piege.jsonl.narration.jsonl", "piege.narration.jsonl"])

print("\n4. Faits : calcules depuis le journal, sources run#seq existantes")
with tempfile.TemporaryDirectory() as d:
    chemin = run_regles(d, "f", jours=3)
    evs = journal.lire(chemin)
    ids = {journal.identifiant(e) for e in evs}
    fens = list(N.parcourir(evs, 1))
    verifier("3 fenetres pour 3 jours", len(fens) == 3)
    fen, av, ap, _ = fens[0]
    table, paroles = N.faits(fen, av, ap)
    r1 = fen[3]
    f1 = table["F1"]
    verifier("le taux du fait F1 est celui du releve", float(round(r1["taux_adoption"] * 100))
             in f1["nombres"] and f1["sources"] == [journal.identifiant(r1)])
    verifier("toutes les sources des faits existent dans le journal",
             all(s in ids for f in list(table.values()) + list(paroles.values())
                 for s in f["sources"]))
    verifier("fenetre 1 : le premier choix d'un agent n'est pas un changement de lecture",
             not [f for f in table.values() if f.get("nature") == "change"])
    noues = [f for f in table.values() if f.get("role") == "noue"]
    if noues:
        e = next(x for x in evs if journal.identifiant(x) == noues[0]["sources"][0])
        verifier("un fait d'adoption renvoie a une decision de porter",
                 e["schema"] == "decision.v1" and e["porte"])

print("\n4 bis. Faits : egalites et emergence")
r0 = {"schema": "indicateurs.v1", "run": "x", "seq": 2, "t_sim": 0, "t_sim_lisible": "J01 00:00",
      "taux_adoption": 0.3, "porteurs": ["a", "b", "c"], "sens_dominant": "ironie",
      "part_sens_dominant": 0.4, "repartition_sens": {"ironie": 4, "tendance": 3, "aucun_sens": 3}}
r1 = {**r0, "seq": 5, "t_sim": 1440, "t_sim_lisible": "J02 00:00", "sens_dominant": "ironie",
      "repartition_sens": {"ironie": 4, "tendance": 4, "aucun_sens": 2}}
et = N.Etat()
et.pop = {k: {"nom": k, "groupe": "g", "moteur": "regles"} for k in "abcdefghij"}
em = {"seuil_persistance": {"six_sens": {"delta_a": 0.14, "seuil": 0.26, "emergent": False},
                            "regroupe": {"delta_a": 0.25, "seuil": 0.22, "emergent": True}},
      "ombres": {}}
bilan = {"schema": "bilan.v1", "run": "x", "seq": 6, "t_sim": 1440}
tf, _ = N.faits((1, [r1, bilan], r0, r1), et, et, em)
sens = next(f for f in tf.values() if f["nature"] == "sens")
verifier("egalite au sommet : les deux sens sont dits", "ironie et tendance a egalite" in sens["texte"])
verifier("pas de bascule annoncee quand le sommet est une egalite",
         not [f for f in tf.values() if f["nature"] == "bascule"])
emf = [f for f in tf.values() if f["nature"] == "emergence"]
verifier("un seul fait d'emergence portant les deux lectures",
         len(emf) == 1 and "six sens" in emf[0]["texte"] and "regroupe" in emf[0]["texte"]
         and emf[0]["emergence"] is False)

print("\n5. Validateur (version 3) : constats repris des faits, lectures controlees")
table = {
    "F1": {"tag": "F1", "texte": "Taux 35 % (7 sur 20).", "nombres": [35.0, 7.0, 20.0],
           "sources": ["r#5"], "agents": [], "nature": "adoption", "proportion": 0.35},
    "F2": {"tag": "F2", "texte": "Variation +20 points.", "nombres": [20.0, 15.0, 35.0],
           "sources": ["r#2", "r#5"], "agents": [], "variation": 0.20, "nature": "variation"},
    "F3": {"tag": "F3", "texte": "Ont noue : Lea (1).", "nombres": [1.0], "sources": ["r#3"],
           "agents": ["Lea"], "role": "noue", "nature": "noue"},
    "F4": {"tag": "F4", "texte": "Emergence : non emergent.", "nombres": [12.0, 24.0],
           "sources": ["r#9"], "agents": [], "emergence": False, "nature": "emergence"},
    "F5": {"tag": "F5", "texte": "Sens le plus donne : tendance (12 sur 20).",
           "nombres": [12.0, 20.0], "sources": ["r#5"], "agents": [], "nature": "sens",
           "proportion": 0.6},
    "F6": {"tag": "F6", "texte": "Aucun etudiant n'a noue, retire ou relu le ruban.",
           "nombres": [], "sources": ["r#4"], "agents": [], "nature": "calme"},
}
paroles = {"P1": {"tag": "P1", "texte": "Karim a ecrit sur le reseau : \"c'est juste une mode\"",
                  "nombres": [], "sources": ["r#4"], "agents": ["Karim"], "role": "parole",
                  "nature": "parole"}}
noms = ["Lea", "Karim", "Sofia"]


def un(b):
    return N.valider([b], table, paroles, noms)[0]


c = un({"type": "observation", "fait": "F1", "texte": "Tout le campus porte le ruban !",
        "sources": []})
verifier("constat : le texte publie est celui du fait, pas celui du modele",
         c["statut"] == "verifiee" and c["texte"] == table["F1"]["texte"]
         and c["texte_modele"] == "Tout le campus porte le ruban !")
verifier("constat : type mesure si le fait porte des nombres, sources du fait",
         c["type"] == "mesure" and c["sources"] == ["r#5"])
c = un({"type": "mesure", "fait": "F6", "texte": "", "sources": []})
verifier("constat sans nombre : type observation", c["type"] == "observation")
c = un({"type": "observation", "fait": "P1", "texte": "", "sources": []})
verifier("constat d'une parole : publiee mot pour mot, type observation",
         c["texte"] == paroles["P1"]["texte"] and c["type"] == "observation")
deux = N.valider([{"type": "observation", "fait": "F1"}, {"type": "observation", "fait": "F1"}],
                 table, paroles, noms)
verifier("un fait choisi deux fois : rejete la seconde fois",
         deux[1]["raison"] == "fait deja cite : F1")
lectures = [
    ("interpretation", "La hausse semble nette.", ["F2"], None),
    ("interpretation", "La plupart semblent lire le ruban comme une tendance.", ["F5"], None),
    ("incertitude", "On ne sait pas pourquoi Lea l'a noue.", ["F3"], None),
    ("incertitude", "Rien ne dit ce que pense le campus.", [], None),
    ("observation", "35 % portent le ruban.", ["F1"], "constat sans fait choisi"),
    ("interpretation", "La hausse est nette.", ["F2"], "interpretation sans conditionnel"),
    ("interpretation", "Deux etudiants semblent hesiter.", ["F1"], "nombre dans une lecture"),
    ("interpretation", "Tous semblent donner le meme sens au ruban.", ["F5"],
     "quantificateur \"tous\" contraire aux faits cites"),
    ("interpretation", "Aucun etudiant ne semble porter le ruban.", ["F1"],
     "quantificateur \"aucun\" contraire aux faits cites"),
    ("interpretation", "La plupart semblent suivre.", ["F2"],
     "quantificateur \"la plupart\" sans proportion citee"),
    ("interpretation", "Karim semble porter le ruban.", ["P1"],
     "action de Karim deduite d'une parole"),
    ("interpretation", "Le ruban semble lu comme une ironie.", ["F2"],
     "source hors sujet (sens du ruban)"),
    ("interpretation", "Sofia pourrait suivre le mouvement.", ["F1"], "personne non sourcee : Sofia"),
    ("interpretation", "Une emergence semble se dessiner.", ["F4"],
     "emergence contraire a l'indicateur"),
    ("interpretation", "Une emergence semble se dessiner.", ["F2"],
     "source hors sujet (emergence)"),
    ("interpretation", "Karim semble ironiser : « le ruban est ringard ».", ["P1"],
     "citation absente des paroles citees"),
    ("interpretation", "L'adoption semble baisser.", ["F2"],
     "baisse contraire a la variation mesuree"),
    ("interpretation", "Le campus semble changer.", ["F9"], "source inconnue : F9"),
    ("interpretation", "Le campus semble changer.", [], "affirmation sans source"),
    ("interpretation", "L'adoption semble se stabiliser.", ["F2"],
     "stabilite contraire a la variation mesuree"),
    ("interpretation", "La hausse pourrait venir d'une influence sociale.", ["F2"],
     "cause suggeree dans une interpretation"),
    ("incertitude", "On ne sait pas si la hausse vient d'une influence sociale.", ["F2"], None),
]
for t, x, s_, attendu in lectures:
    r = un({"type": t, "fait": "", "texte": x, "sources": s_})
    verifier(f"{'accepte' if attendu is None else 'rejete'} : {x[:52]}",
             r["raison"] == attendu if attendu else r["statut"] == "verifiee", r["raison"])
trop = N.valider([{"type": "observation", "fait": f"F{i}"} for i in range(1, 7)]
                 + [{"type": "observation", "fait": "P1"}], table, paroles, noms)
verifier("au-dela de 6 affirmations : rejet", trop[-1]["raison"] == "au-dela de 6 affirmations")
verifier("une reponse qui n'est pas une liste ne donne rien", N.valider("texte", table, paroles,
                                                                        noms) == [])

print("\n6. Erreurs du modele : la narratrice continue, rien n'est invente")
with tempfile.TemporaryDirectory() as d:
    chemin = run_regles(d, "e", jours=2)
    fen, av, ap, _ = next(N.parcourir(journal.lire(chemin), 1))
    for nom, c, attendu in (
            ("modele sans reponse", ClientFactice(None), "incident"),
            ("delai depasse", ClientFactice(erreur=TimeoutError()), "incident"),
            ("connexion coupee", ClientFactice(erreur=ConnectionError()), "incident"),
            ("reponse sans affirmations", ClientFactice({"x": 1}), "incident"),
            ("aucune affirmation verifiable", ClientFactice({"affirmations": [
                {"type": "mesure", "texte": "99 % !", "sources": ["F1"]}]}), "vide"),
            ("sans modele", None, "incident")):
        n = N.narrer(c, fen, av, ap)
        verifier(f"{nom} -> statut {attendu}, texte vide", n["statut"] == attendu
                 and n["texte"] == "", (n["statut"], n["incident"]))

print("\n7. Rejeu : relu et revalide sans aucun appel au modele")
with tempfile.TemporaryDirectory() as d:
    chemin = run_regles(d, "rj", jours=3)
    evs = journal.lire(chemin)

    def repondre(consigne):
        # Reprend le taux du fait F1 tel que la consigne l'ecrit.
        ligne = next(l for l in consigne.splitlines() if l.startswith("[F1]"))
        pct = ligne.split(": ")[1].split(" %")[0]
        assert pct
        return {"affirmations": [
            {"type": "observation", "fait": "F1", "texte": "", "sources": []},
            {"type": "interpretation", "fait": "", "texte": "Le campus semble ravi a 99 %.",
             "sources": ["F1"]}]}
    c = ClientFactice(repondre)
    sortie = os.path.join(d, "rj.narration.jsonl")
    s = N.Sortie(sortie, "rj", chemin)
    s.ecrire("narratrice.v1", source=chemin, empreinte_source=N.sha256(chemin), mode="post",
             periode=1, taille="llm_grand", modele="factice", temperature=0.3,
             empreinte_prompt=N.EMPREINTE_PROMPT, version_contrat=contrat.VERSION_CONTRAT)
    for fen, av, ap, em in N.parcourir(evs, 1):
        s.narration(N.narrer(c, fen, av, ap, emergence=em))
    s.fermer()
    lignes = [json.loads(l) for l in open(sortie, encoding="utf-8")]
    verifier("en-tete puis 3 narrations conformes au contrat",
             [e["schema"] for e in lignes] == ["narratrice.v1"] + ["narration.v1"] * 3
             and all(contrat.verifier(dict(e))[0] for e in lignes))
    verifier("chaque narration : 1 constat verifie, 1 lecture rejetee (statut partiel)",
             all(e["statut"] == "partiel" for e in lignes[1:]))
    appels = len(c.consignes)
    _, narrations, ecarts = N.rejouer(sortie, chemin)
    verifier("rejeu identique au recalcul (0 ecart)", not ecarts, ecarts)
    verifier("aucun appel au modele pendant le rejeu", len(c.consignes) == appels)
    # Dans un processus neuf, modele injoignable : le client LLM n'est meme pas importe.
    code = ("import sys, narratrice; sys.argv=['n','--rejeu',%r,'--journal',%r];"
            "r=narratrice.main(); print('LLM_IMPORTE' if 'ephemere.llm' in sys.modules "
            "else 'LLM_ABSENT'); sys.exit(r)") % (sortie, chemin)
    p = subprocess.run([sys.executable, "-c", code], cwd=RACINE, capture_output=True, text=True,
                       env={**os.environ, "OLLAMA_URL": "http://127.0.0.1:9/v1/chat/completions"})
    verifier("narratrice.py --rejeu : code 0, client LLM jamais importe",
             p.returncode == 0 and "LLM_ABSENT" in p.stdout, p.stdout[-300:] + p.stderr[-300:])
    # Une narration retouchee a la main est detectee.
    lignes[2]["texte"] = "[mesure] 100 % des etudiants portent le ruban."
    with open(sortie, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(e) + "\n" for e in lignes)
    _, _, ecarts = N.rejouer(sortie, chemin)
    verifier("une narration retouchee est signalee au rejeu",
             ecarts == [("N2", "texte different")], ecarts)
    lignes[3]["modele"]["validateur"] = 1
    with open(sortie, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(e) + "\n" for e in lignes)
    _, _, ecarts = N.rejouer(sortie, chemin)
    verifier("une narration d'une autre version du validateur est signalee comme telle",
             ("N3", "validee par la version 1 du validateur, version actuelle "
              f"{N.VERSION_VALIDATEUR}") in ecarts, ecarts)

print("\n8. Affichage : le recit principal ne montre que les constats")
import contextlib  # noqa: E402
import io  # noqa: E402
import narratrice  # noqa: E402
n = {"narration": "N1", "fenetre": {"debut": "J01 00:00", "fin": "J02 00:00"}, "statut": "partiel",
     "incident": None, "sources": [], "texte": "[mesure] constat\n[interpretation] lecture",
     "affirmations": [
         {"type": "mesure", "texte": "constat chiffre", "statut": "verifiee"},
         {"type": "observation", "texte": "constat observe", "statut": "verifiee"},
         {"type": "interpretation", "texte": "lecture prudente", "statut": "verifiee"},
         {"type": "incertitude", "texte": "doute exprime", "statut": "verifiee"},
         {"type": "interpretation", "texte": "lecture rejetee", "statut": "rejetee", "raison": "r"}]}
canaux = narratrice.recit(n)
verifier("trois canaux : constats, hypotheses, incertitudes ; rejetees exclues",
         [len(canaux[k]) for k in ("constats", "hypotheses", "incertitudes")] == [2, 1, 1]
         and all(a["statut"] == "verifiee" for v in canaux.values() for a in v))
for hyp in (False, True):
    sortie = io.StringIO()
    with contextlib.redirect_stdout(sortie):
        narratrice.afficher(n, hypotheses=hyp)
    vu = sortie.getvalue()
    if not hyp:
        verifier("par defaut : constats affiches, hypotheses et incertitudes masquees",
                 "constat chiffre" in vu and "constat observe" in vu
                 and "lecture prudente" not in vu and "doute exprime" not in vu
                 and "lecture rejetee" not in vu and "masquee" in vu, vu)
    else:
        verifier("--hypotheses : affichees a part, annoncees comme hypothese ou incertitude",
                 "(hypothese, non verifiee) lecture prudente" in vu
                 and "(incertitude) doute exprime" in vu and "lecture rejetee" not in vu, vu)

print()
if echecs:
    print(f"{len(echecs)} verification(s) en echec.")
    sys.exit(1)
print("Toutes les verifications passent.")
