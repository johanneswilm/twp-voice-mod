# Thimbleweed Park - character to voice mapping

Voice assignment for the German and Spanish TTS voice mods. `gender` is the
character's in-game gender: male characters get male voices, female characters
female ones. Genders were cross-checked against public character lists
(Thimbleweed Park wiki); three low-voiced women (Agent Ray, Sandy, Lenore) were
initially mis-assigned male voices by the pitch heuristic and are marked below.

The full recipe to regenerate audio lives in the repository README. Voice model
quality notes (which piper models garble, which are clean) are in `voice_quality.json`.

| Actor key | Character | Gender | German voice | Spanish voice | Notes |
|---|---|---|---|---|---|
| `BANKMANAGER` | Bankmanager | m | `de_DE-pavoque-low`, pitch ×0.84, speed ×1.0 | `es_ES-davefx-medium`, pitch ×0.94, speed ×1.04 |  |
| `BORIS` | Boris | m | `de_DE-thorsten-medium`, pitch ×1.0, speed ×0.96 | `es_MX-ald-medium`, pitch ×0.88, speed ×0.96 | Boris Schultz (wiki) |
| `BRETT` | Brett | m | `de_DE-thorsten-high`, pitch ×0.84, speed ×1.0 | `es_MX-ald-medium`, pitch ×0.97, speed ×0.96 |  |
| `CARNEY` | Carney | f | `de_DE-thorsten_emotional-medium`, speaker 2, pitch ×1.0, speed ×1.0 | `es_MX-claude-high`, pitch ×1.0, speed ×1.0 |  |
| `CASSIE` | Cassie | f | `de_DE-mls-medium`, speaker 37, pitch ×1.04, speed ×1.04 | `es_ES-sharvard-medium`, speaker 1, pitch ×1.0, speed ×1.04 |  |
| `CHET` | Chet | m | `de_DE-pavoque-low`, pitch ×1.04, speed ×1.0 | `es_ES-sharvard-medium`, speaker 0, pitch ×0.94, speed ×0.96 | Chet Lockdown (wiki) |
| `CHUCK` | Chuck Edmund | m | `de_DE-thorsten_emotional-medium`, speaker 4, pitch ×1.0, speed ×1.0 | `es_ES-sharvard-medium`, speaker 0, pitch ×1.0, speed ×1.0 |  |
| `COMPUTER` | Computer | f | `de_DE-ramona-low`, pitch ×0.92, speed ×1.0 | `es_MX-claude-high`, pitch ×1.02, speed ×1.0 |  |
| `CORONER` | Coroner | f | `de_DE-thorsten_emotional-medium`, speaker 2, pitch ×1.04, speed ×1.0 | `es_ES-mls_9972-low`, pitch ×1.0, speed ×1.0 |  |
| `DAVE` | Dave | m | `de_DE-thorsten_emotional-medium`, speaker 4, pitch ×0.92, speed ×1.0 | `es_MX-ald-medium`, pitch ×0.84, speed ×0.96 |  |
| `DAVIDFOX` | Davidfox | m | `de_DE-thorsten-high`, pitch ×0.88, speed ×1.0 | `es_ES-sharvard-medium`, speaker 0, pitch ×1.06, speed ×0.96 |  |
| `DELORES` | Delores | f | `de_DE-thorsten_emotional-medium`, speaker 2, pitch ×1.1, speed ×1.0 | `es_AR-daniela-high`, pitch ×1.0, speed ×1.0 |  |
| `DOUG` | Doug | m | `de_DE-thorsten-medium`, pitch ×0.96, speed ×0.96 | `es_ES-davefx-medium`, pitch ×1.06, speed ×0.96 |  |
| `DRAGON` | Dragon | f | `de_DE-thorsten_emotional-medium`, speaker 1, pitch ×1.0, speed ×1.0 | `es_AR-daniela-high`, pitch ×1.06, speed ×1.04 |  |
| `EDNA` | Edna Edmund | f | `de_DE-kerstin-low`, pitch ×1.0, speed ×1.0 | `es_ES-mls_9972-low`, pitch ×1.06, speed ×0.96 |  |
| `FEMALEGHOST1` | Femaleghost1 | f | `de_DE-kerstin-low`, pitch ×1.08, speed ×1.0 | `es_ES-mls_10246-low`, pitch ×1.0, speed ×0.96 |  |
| `FRANKLIN` | Franklin Edmund | m | `de_DE-pavoque-low`, pitch ×1.0, speed ×1.0 | `es_MX-ald-medium`, pitch ×1.0, speed ×1.0 | Franklin Edmund (ghost), playable |
| `FUJICO` | Fujico | m | `de_DE-thorsten_emotional-medium`, speaker 5, pitch ×1.0, speed ×1.0 | `es_ES-davefx-medium`, pitch ×1.12, speed ×0.96 | f0-detected; few lines |
| `GARYWINNICK` | Garywinnick | m | `de_DE-thorsten-high`, pitch ×0.92, speed ×1.0 | `es_MX-ald-medium`, pitch ×0.91, speed ×1.04 |  |
| `HEADGHOST` | Headghost | m | `de_DE-karlsson-low`, pitch ×1.0, speed ×0.92 | `es_ES-sharvard-medium`, speaker 0, pitch ×0.86, speed ×0.92 |  |
| `HINTTRON` | Hinttron | m | `de_DE-mls-medium`, speaker 23, pitch ×1.0, speed ×1.06 | `es_MX-ald-medium`, pitch ×1.02, speed ×1.06 |  |
| `HOTELKID` | Hotel Kid (Rikki) | f | `de_DE-thorsten_emotional-medium`, speaker 1, pitch ×0.92, speed ×1.0 | `es_AR-daniela-high`, pitch ×1.15, speed ×0.95 | hotel kid (Rikki) |
| `HOTELMANAGER` | Hotel Manager | m | `de_DE-karlsson-low`, pitch ×1.04, speed ×1.04 | `es_MX-ald-medium`, pitch ×0.81, speed ×1.04 |  |
| `KENTHIEN` | Kenthien | m | `de_DE-thorsten_emotional-medium`, speaker 4, pitch ×1.08, speed ×1.0 | `es_ES-sharvard-medium`, speaker 0, pitch ×0.88, speed ×1.0 |  |
| `LAWYER` | Lawyer | m | `de_DE-pavoque-low`, pitch ×0.96, speed ×1.0 | `es_MX-ald-medium`, pitch ×0.86, speed ×0.96 |  |
| `LENORE` | Lenore | f | `de_DE-kerstin-low`, pitch ×0.96, speed ×1.0 | `es_ES-mls_10246-low`, pitch ×1.1, speed ×1.0 | Lenore Edmund-Mulch, Delores' grandmother (wiki); low voice (162 Hz) - corrected to female |
| `LEONARD` | Leonard | m | `de_DE-pavoque-low`, pitch ×1.08, speed ×1.0 | `es_ES-sharvard-medium`, speaker 0, pitch ×1.12, speed ×0.96 |  |
| `LOOKALIKE1` | Lookalike1 | f | `de_DE-thorsten_emotional-medium`, speaker 1, pitch ×1.08, speed ×1.0 | `es_ES-mls_9972-low`, pitch ×1.12, speed ×1.04 |  |
| `LOOKALIKE2` | Lookalike2 | f | `de_DE-ramona-low`, pitch ×1.0, speed ×1.0 | `es_ES-mls_9972-low`, pitch ×0.97, speed ×1.0 |  |
| `MADAMEMORENA` | Madame Morena | f | `de_DE-kerstin-low`, pitch ×1.04, speed ×1.0 | `es_AR-daniela-high`, pitch ×1.12, speed ×1.0 |  |
| `MALEGHOST1` | Maleghost1 | m | `de_DE-thorsten_emotional-medium`, speaker 6, pitch ×1.0, speed ×1.0 | `es_ES-sharvard-medium`, speaker 0, pitch ×0.97, speed ×0.96 |  |
| `MIME` | Mime | f | `de_DE-thorsten_emotional-medium`, speaker 1, pitch ×1.04, speed ×1.0 | `es_AR-daniela-high`, pitch ×0.97, speed ×1.0 |  |
| `NATALIE` | Natalie | m | `de_DE-thorsten-medium`, pitch ×1.04, speed ×1.0 | `es_ES-sharvard-medium`, speaker 0, pitch ×1.03, speed ×1.0 | newspaper editor; borderline pitch (170 Hz), f0-detected |
| `PIGEON1` | Pigeon1 | m | `de_DE-thorsten-high`, pitch ×1.04, speed ×1.0 | `es_ES-davefx-medium`, pitch ×0.97, speed ×0.96 |  |
| `PIGEON2` | Pigeon2 | m | `de_DE-thorsten_emotional-medium`, speaker 4, pitch ×1.04, speed ×1.0 | `es_ES-sharvard-medium`, speaker 0, pitch ×0.84, speed ×0.96 |  |
| `POSTALWORKER` | Postalworker | f | `de_DE-ramona-low`, pitch ×1.08, speed ×1.0 | `es_ES-sharvard-medium`, speaker 1, pitch ×0.94, speed ×1.0 |  |
| `RANSOME` | Ransome the Clown | m | `de_DE-thorsten-medium`, pitch ×1.1, speed ×1.0 | `es_ES-davefx-medium`, pitch ×1.2, speed ×0.95 | Ransome the Clown, playable |
| `RAY` | Agent Ray | f | `de_DE-thorsten_emotional-medium`, speaker 2, pitch ×0.96, speed ×1.0 | `es_ES-sharvard-medium`, speaker 1, pitch ×1.0, speed ×1.0 | Special Agent Angela Ray - female (wiki; corrected after user reported male voice) |
| `REYES` | Antonio Reyes | m | `de_DE-thorsten-medium`, pitch ×0.84, speed ×1.0 | `es_MX-ald-medium`, pitch ×0.94, speed ×1.0 | Antonio Reyes, playable |
| `REYESMOM` | Reyesmom | f | `de_DE-thorsten_emotional-medium`, speaker 7, pitch ×1.0, speed ×1.0 | `es_ES-mls_10246-low`, pitch ×0.94, speed ×0.96 | Antonio Reyes' mother |
| `RICKI` | Ricki | f | `de_DE-thorsten_emotional-medium`, speaker 1, pitch ×0.88, speed ×1.0 | `es_MX-claude-high`, pitch ×1.06, speed ×1.04 |  |
| `RONGILBERT` | Rongilbert | m | `de_DE-karlsson-low`, pitch ×1.09, speed ×1.0 | `es_ES-davefx-medium`, pitch ×1.03, speed ×1.0 |  |
| `ROOMGUEST` | Roomguest | f | `de_DE-ramona-low`, pitch ×1.04, speed ×1.0 | `es_ES-mls_9972-low`, pitch ×1.16, speed ×0.96 |  |
| `SANDY` | Sandy | f | `de_DE-thorsten_emotional-medium`, speaker 1, pitch ×0.92, speed ×1.0 | `es_AR-daniela-high`, pitch ×0.9, speed ×1.0 | Delores' mother (wiki); low voice (159 Hz) fooled f0 detector - corrected to female |
| `SHERIFF` | Sheriff | f | `de_DE-thorsten_emotional-medium`, speaker 7, pitch ×1.08, speed ×1.0 | `es_AR-daniela-high`, pitch ×1.16, speed ×1.0 |  |
| `STARSHIPMAN` | Starshipman | m | `de_DE-thorsten-high`, pitch ×1.08, speed ×1.0 | `es_ES-davefx-medium`, pitch ×0.84, speed ×0.96 |  |
| `TRONMACHINE` | Tron Machine | m | `de_DE-thorsten_emotional-medium`, speaker 5, pitch ×0.92, speed ×1.0 | `es_ES-davefx-medium`, pitch ×0.88, speed ×0.9 |  |
| `WILLIE` | Willie | m | `de_DE-pavoque-low`, pitch ×0.9, speed ×1.0 | `es_ES-davefx-medium`, pitch ×1.16, speed ×1.0 |  |

## Gender determination method

1. Pitch (F0) measurement of the original English voice lines per actor - works for
   most characters (male voices cluster 90-160 Hz, female 165-260 Hz).
2. Cross-check against public character lists and story context.
3. Corrections where a character's canon gender contradicts their measured pitch
   (three deep-voiced female characters so far: Agent Ray, Sandy, Lenore).
