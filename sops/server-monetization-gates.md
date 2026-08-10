# SOP - Verrous serveur de monétisation

Sources: ACTION_TRACKER + session 2026-08-07 soir.

Objectif: le Mode Examen ne doit pas être déverrouillable uniquement côté client.

1. Corriger le quota gratuit:
   - trouver la route qui traite `action: cancel` ;
   - remplacer la suppression `prisma.timeEntry.delete(...)` par un statut `cancelled` ;
   - vérifier que la ligne compte encore dans le quota.
2. Ajouter le gating serveur `examModeEnabled` sur les routes qui créent ou lancent une session Mode Examen.
3. Auditer `AIService.ts`:
   - il crée `TimeEntry` et `DeepWorkSession` en direct ;
   - ajouter les mêmes limites de plan que le parcours normal ;
   - empêcher les sessions IA de 240 min pour les gratuits si non autorisé.
4. Tester en compte gratuit.
5. Déployer avec `vercel --prod`.
6. Preuve attendue: commit + test gratuit + prod vérifiée.

