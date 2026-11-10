# Fixture: U2 sample cardinals

Synthetic named stills under `frames/` for pack-builder smoke:

```bash
python -m composite3dgen build-packs fixtures/u2-sample --executor local
```

Expects identical `build_packs/{triposr,tripo,hi3d,rodin}/` with `README.md` +
`front.jpg` / `left.jpg` / `back.jpg` / `right.jpg`.
