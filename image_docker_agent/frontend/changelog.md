## Version en date du 27/08/2026
### Version 0.2
L'outil a été retravaillé de fond en comble :
- Vous pouvez donner des instructions de génération avant de commencer le processus
- La génération repose sur des agents qui vont s'occuper d'extraire les informations sur lesquelles ils sont spécialisés
- Après la génération, vous avez un aperçu sur l'interface 
- Vous pouvez écrire des instructions pour modifier le compte-rendu généré

## Version en date du 25/06/2026
### Ajout d'un système de file d'attente pour la transcription
Puisque la transcription est gourmand en mémoire, j'ai mis un système de file d'attente pour réduire l'utilisation de l'outil à 1 personne à la fois tout en indiquant aux utilisateurs que l'outil fonctionne et ne tourne pas dans le vide. A noter que la file d'attente ne concerne que l'outil de transcription, il n'y a pas cette limite sur l'outil de génération de compte-rendu donc en ayant un transcript texte vous n'avez pas à attendre dans cette file.


## Version en date du 24/06/2026
### Ajout d'un mode de traitement "automatique"
Maintenant, par défaut, lorsque vous lancez la transcription de votre fichier audio/vidéo ou uploader transcript texte, tous les processus d'extraction et d'analyses se feront automatiquement jusqu'à la génération du compte-rendu incluse. Vous pouvez néanmoins désactiver l'option dans la marge.

## Version en date du 11/06/2026
### Ajout du manuel d'utilisation dans l'application
Une nouvelle page "Manuel" a été ajoutée dans laquelle se trouve le mode d'emploi de l'outil de Compte-rendu.


## Version en date du 27/05/2026
### Ajout de la page snapshot
Cette nouvelle page fonctionne comme la précédente : elle rédige un compte-rendu à partir d'un fichier audio/vidéo. C'est la logique derrière qui rend cette page différente, cette page tente d'imiter le comportement d'un humain.  
Voilà le workflow de chaque page :  


| Page | Workflow |
| :--- | :--- | 
| **App** | L'IA divise la transcription en morceaux => l'IA rédige un résumé très dense en information => Chaque résumé est vérifié à nouveau par l'IA pour s'assurer que toutes les informations sont bien présentes => L'IA génère le compte-rendu final à partir des résumés précédents |
| **snapshot** | L'IA divise la transcription en morceaux => l'IA rédige des notes pour chaque morceau => A partir de chacune des notes l'IA rédige un compte-rendu.|