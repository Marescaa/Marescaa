# El gato del perfil

`make_cat.py` dibuja un gatito pixel-art (`cat.gif`, 400×220, fondo transparente) y la
Action `.github/workflows/cat.yml` lo regenera todas las noches.

## Pelaje (`CAT_COAT`)

| Nombre    | Gato                                  |
|-----------|---------------------------------------|
| `auto`    | Se deduce del lenguaje principal de tus repos públicos (default) |
| `gray`    | Gris                                  |
| `orange`  | Naranja atigrado                      |
| `calico`  | Calicó (blanco con manchas negras y naranjas) |
| `siamese` | Siamés (crema con máscara, orejas y cola oscuras) |
| `white`   | Blanco                                |
| `tuxedo`  | Esmoquin (negro con pecho, hocico y patas blancas) |
| `black`   | Negro                                 |
| `brown`   | Marrón atigrado                       |

`auto`: Python, Jupyter, R, Julia, MATLAB → `orange` · Shell, PowerShell, Ruby, Perl, PHP, Lua → `brown` ·
JavaScript, TypeScript, HTML, CSS, Vue, Svelte → `calico` · C, C++, Rust, Go, Zig → `tuxedo` ·
Java, Kotlin, Swift, C#, Dart, Scala → `siamese` · cualquier otro → uno fijo elegido por hash.
Si la API falla, sale `orange`.

## Estado según tus contribuciones (últimos 7 días completos)

| Contribuciones | Estado     | Qué hace |
|----------------|------------|----------|
| 0–2            | `calm`     | Sentado: parpadea, mueve la cola y la cabeza, levanta la patita y se la lame |
| 3–6            | `happy`    | Camina de un lado a otro con la cola arriba; en cada punta se sienta, corazoncitos y se da vuelta |
| 7–13           | `euphoric` | Trota rápido de un lado a otro, inclinado hacia adelante, con destellos; en cada punta un saltito de festejo en el lugar |
| 14 o más       | `king`     | Corona y aura de brillos; camina con porte y en una punta hace un salto con giro en el lugar |
| (manual)       | `sleep`    | Dormido acostado como un pancito, respirando, con "z z z" (solo si lo elegís a mano) |

Los umbrales son las constantes `CALM_MAX`, `HAPPY_MAX` y `EUPHORIC_MAX` al principio de `make_cat.py`.

## Cómo cambiarlo

- **Una vez:** Actions → *Cat* → *Run workflow* y elegí `coat` / `state`.
- **Para siempre:** Settings → Secrets and variables → Actions → *Variables* y creá
  `CAT_COAT` (por ejemplo `calico`) o `CAT_STATE` (por ejemplo `sleep`). También podés cambiar
  el `'auto'` de `cat.yml`.
- **Local:**

  ```sh
  python cat/make_cat.py 5 --coat calico          # 5 contribuciones, pelaje calicó
  python cat/make_cat.py --state sleep --coat black
  GITHUB_TOKEN=$(gh auth token) KOI_LOGIN=tu-usuario python cat/make_cat.py   # datos reales
  ```

  `CAT_OUT` cambia la ruta del GIF (default `cat/cat.gif`).
