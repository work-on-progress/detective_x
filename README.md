# Detective X

Fifteen investigations, played in the browser. Search locations, interview
suspects, catch them contradicting each other, weigh how much each piece of
evidence can be trusted, and name the culprit.

The whole game engine is Python. In the browser it runs on WebAssembly, so
there is no server, nothing is sent anywhere, and the site is a set of static
files GitHub Pages can host on its own.

**Play it:** `https://<your-username>.github.io/detective-x/`

---

## What is in here

| | |
|---|---|
| Cases | 15, from Easy to Expert |
| Language | Python 3.10+ |
| Runtime dependencies | none — the standard library only |
| Browser runtime | Pyodide (CPython on WebAssembly), loaded from a CDN |
| Machine learning | Naive Bayes and logistic regression, written from scratch |
| Tests | 85, run on every push |
| Hosting | GitHub Pages, no build step, no server |

The same engine drives two front-ends: a terminal build you run locally and a
browser build you deploy. Neither one contains any game logic, which is the
whole point of the architecture.

---

## Deploying it

1. Create a repository and push this directory to `main`.
2. In **Settings → Pages**, set **Source** to **GitHub Actions**.
3. Push. The `deploy` workflow rebuilds the case data, refuses to publish if
   any test fails or any case turns out to be unsolvable, and puts the site up.

Nothing else is required. There is no build tool, no bundler and no package
install.

> **Keep `.nojekyll`.** GitHub Pages runs Jekyll by default, and Jekyll deletes
> every file whose name begins with an underscore — which would remove every
> `__init__.py` and break the Python package. The empty `.nojekyll` file in the
> repository root is what stops that.

---

## Playing it in a terminal

```bash
git clone https://github.com/<your-username>/detective-x.git
cd detective-x
python -m detective_x
```

No installation, no virtual environment, no dependencies.

```bash
python -m detective_x --case 3          # open a case directly
python -m detective_x --debug           # reveal everything, fix the random seed
python -m detective_x --ascii           # plain borders for older terminals
python -m detective_x --no-animation    # skip the loading effects
python -m detective_x --no-colour       # or set NO_COLOR=1
python -m detective_x --save ~/dx-saves # keep saves somewhere else
```

---

## How it is built

```
detective_x/
├── models/        what things are      — Case, Suspect, Evidence, enums
├── engine/        what happens         — scoring, deduction, the ML model
├── persistence/   what is remembered   — atomic file saves, browser storage
├── ui/            what is shown        — terminal screens, browser facade
└── data/cases/    fifteen case files
```

One rule holds the whole thing together:

> **The engine layer never prints and never reads input.**

It takes data and returns data. The terminal layer turns that into boxes; the
browser layer turns it into HTML. This is not a stylistic preference — it is
what makes the game logic testable, and it is why the same code runs in a
terminal and in a browser without a single change. A test enforces it, so it
cannot quietly rot.

```
  ui/        may use models and config
   ↑
  engine/    may use models, config, exceptions — never ui/
   ↑
  models/    may use enums and config — never engine/ or ui/
```

### The deduction engine

`engine/analyst.py` contains a small machine learning model with no
dependencies at all: a Gaussian Naive Bayes classifier and a logistic
regression trained by batch gradient descent, both written out in plain Python.

It reads eight features per suspect — the weight of evidence against them, its
average reliability, how much of the case's evidence points their way, how many
contradictions they are caught in, and so on — and returns a probability that
they are the culprit, along with the three features driving that figure.

The interesting part is the training. **The case you are currently playing is
removed from the training set before the model is fitted.** It has never seen
the answer to your case; it has only seen what guilt looked like in the other
fourteen. That makes its opinion worth something, and it also makes it possible
to measure:

```
$ python tools/verify.py
deduction engine, leave-one-case-out: 15/15 (100%)
```

It is deliberately presented in-game as a colleague's opinion rather than an
answer, and it tells you when it does not have enough evidence to be useful.

### The cases

Case files are plain JSON in `detective_x/data/cases/`. The engine loads any
valid case file without a code change — if adding a case required editing the
engine, the design would have failed.

They are written as readable Python in `tools/cases_*.py` and compiled to JSON,
because forty-one nested dictionaries per case is not something anyone should
hand-write:

```bash
python tools/build_cases.py     # regenerate the JSON
python tools/build_manifest.py  # regenerate the browser's file list
```

Every case is validated at load time against nine structural rules — the
culprit must be a suspect, every prerequisite must exist, every clue must be
reachable, at least one clue must implicate the culprit. A case that fails any
of them is rejected rather than shipped, and CI plays all fifteen through to a
correct solution before anything is published.

---

## Running the tests

```bash
python -m unittest discover -s tests -t . -v
python tools/verify.py
```

The suite covers scoring arithmetic, contradiction detection, suspicion
scoring, the ML model, case validation, save corruption and recovery, and a
full scripted playthrough of every case. Two of the tests are worth singling
out:

- **`test_every_case_can_be_played_to_a_correct_solution`** plays all fifteen
  cases through the real engine and fails if any of them cannot be won. This is
  the test that catches story-design mistakes, which otherwise only surface
  when a player gets permanently stuck.
- **`test_no_engine_module_prints_or_reads_input`** enforces the layer rule
  above, so the architecture cannot decay into a pile of `print` statements.

The tests found four genuine bugs while this was being built, including a
contradiction that could never be earned and a red herring that pointed at the
actual culprit.

---

## Design notes

**Reliability is not decoration.** A witness statement at 72% contributes less
suspicion than an access log at 100%. Weight is scaled by reliability
everywhere, including inside the ML features.

**Red herrings clear themselves.** Each one has a matching clue that neutralises
it. Until you find that clue, the wrong suspect keeps rising.

**Contradictions must be earned.** They are latent in the data from the start,
but you only discover one by hearing both accounts. An early version awarded
them silently at the beginning of the case; a test caught it.

**Ratings are relative to the case.** A big case can yield more points than a
small one, so stars are measured against a per-case maximum rather than a fixed
number.

**Expert cases hide the suspicion meter** and cut you to a single hint. You have
to hold the reasoning yourself.

---

## Credits and licence

Case content, engine and interface written for this project. Released under the
MIT Licence — see `LICENSE`.

Pyodide is loaded from jsDelivr and is licensed separately by its authors.
