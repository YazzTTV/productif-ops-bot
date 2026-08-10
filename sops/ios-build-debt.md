# SOP - Dette build iOS

Sources: ACTION_TRACKER + brief Arthur.

Problème: `ios/Productifio.xcodeproj` est gitignoré et `fix-embed-extensions-order.js` doit tourner après chaque `pod install`.

Objectif: ne plus dépendre du disque de Noah.

1. Auditer `scripts/fix-embed-extensions-order.js`.
2. Câbler son exécution dans un config plugin ou un hook `post_install` Podfile.
3. Vérifier qu'un prebuild propre applique le correctif.
4. Vérifier que le cycle `Productifio` ne revient pas.
5. Documenter la commande de build fiable.
6. Preuve attendue: commit + build ou simulation prebuild validée.

