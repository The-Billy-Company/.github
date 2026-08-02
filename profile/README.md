# The Billy Company

We build Billy: an AI that is actually yours. It carries interior state across
sessions instead of resetting to a blank prompt, learns you from what it sees
and hears, and acts before you ask. A life operating system, not a chat box.

Billy lives in a private monorepo. This org is where the pieces that stand on
their own get to leave it.

## What's out here

A package earns its own repo when it is true on its own terms: a contract
someone can hold it to, a benchmark it wins against the obvious incumbent, and
a reason to exist for a person who has never heard of Billy. Until it clears
that bar it stays inside, where being wrong is cheap.

Today that is the search stack we use to read our own code:

- **[irregex](https://github.com/The-Billy-Company/irregex)** - the regex
  engine, and the toolkit of parts underneath one.
- **[gist](https://github.com/The-Billy-Company/gist)** - indexed pattern
  search over a live tree; a drop-in for ripgrep.

The [repository list](https://github.com/orgs/The-Billy-Company/repositories)
is the real inventory. This page will lag it; that is fine.

## How we build

- **Contracts first.** Schemas, protos, and DSLs are the source of truth. Code
  is generated from them, and a drift gate fails the build when the two
  disagree.
- **Beat the incumbent.** We do not ship a claim we have not measured against
  the best thing that already exists. The numbers live in the repo, and a
  regression fails CI like a broken test.
- **Fail open, never wrong.** Indexes, caches, and daemons are allowed to save
  work. They are not allowed to change the answer. When an accelerator cannot
  prove itself safe, it steps aside and the slow path runs.
- **Write the proof before the code.** Every non-obvious idea gets a dossier -
  the claim, the prior art, and what would falsify it - and the thing gets
  built only if the dossier survives.

## License

Apache 2.0 unless a repo says otherwise. Billy itself is proprietary.
Vulnerabilities go to the `SECURITY.md` in the repo they affect.

[billylives.com](https://billylives.com)
