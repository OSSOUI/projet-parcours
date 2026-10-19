"""Horloge simulee et echeancier (exigences C3 et C4).

Le temps de Tessaline se compte en MINUTES SIMULEES depuis J1 00:00.
Il ne suit pas l'horloge reelle : un run de 40 jours simules peut durer
10 minutes reelles, et l'inverse est vrai aussi quand le LLM rame.

Deux modes d'execution, choisis au lancement :
  - synchrone  : tous les agents decident au meme pas de temps ;
  - asynchrone : chacun decide a sa propre cadence, et le temps que met
    le modele a repondre est converti en temps simule.
"""
import heapq

MINUTES_PAR_JOUR = 24 * 60


class Horloge:
    """Le temps simule du monde. Une seule instance par run."""

    def __init__(self, minutes=0):
        self.minutes = int(minutes)

    @property
    def jour(self):
        return self.minutes // MINUTES_PAR_JOUR + 1

    @property
    def heure(self):
        reste = self.minutes % MINUTES_PAR_JOUR
        return reste // 60, reste % 60

    def lisible(self):
        h, m = self.heure
        return f"J{self.jour:02d} {h:02d}:{m:02d}"

    def avancer(self, minutes):
        self.minutes += int(minutes)

    def aller_a(self, minutes):
        if minutes < self.minutes:
            raise ValueError("l'horloge simulee ne recule pas")
        self.minutes = int(minutes)


class Echeancier:
    """File des prochains reveils d'agents, triee par moment simule.

    Le compteur de sequence departage deux agents reveilles a la meme
    minute simulee : sans lui, l'ordre depend du hasard et le run n'est
    plus reproductible (exigence E3).
    """

    def __init__(self):
        self._file = []
        self._seq = 0

    def planifier(self, t_sim, agent_id):
        heapq.heappush(self._file, (int(t_sim), self._seq, agent_id))
        self._seq += 1

    def prochain(self):
        if not self._file:
            return None
        t_sim, _, agent_id = heapq.heappop(self._file)
        return t_sim, agent_id

    def __len__(self):
        return len(self._file)
