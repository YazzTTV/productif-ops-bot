# SOP - Pricing landing + Vercel

Source: weekly recap 2026-08-09 + ACTION_TRACKER.

1. Ouvrir `lib/pricing.ts` dans le repo productif.io.
2. Décaler la date de début affichée si le 15 août n'est plus tenable.
3. Corriger l'économie annuelle : 7,99 x 12 = 95,88 ; (95,88 - 59) / 95,88 = 38,5 %.
4. Vérifier que la landing `/mode-examen` ne contient plus une promesse de prix fausse.
5. Commit.
6. Déployer avec `vercel --prod`. Un `git push` ne déploie pas.
7. Preuve attendue: commit + URL prod vérifiée.

