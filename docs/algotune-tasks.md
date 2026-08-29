# AlgoTune task list

All **154** tasks in `algotune@1.0`, as vendored under
`results/trusted-tasks/algotune/` (gitignored — see the note at the end).

Source: [AlgoTune](https://github.com/oripress/AlgoTune) ·
[paper](https://arxiv.org/abs/2507.15887) · [site](https://algotune.io/) ·
Harbor registry `algotune@1.0`, tasks from `laude-institute/harbor-datasets`
at commit `479f07dd`.

## Shape of the set

| Property | Value |
|---|---|
| Tasks | 154 |
| Declared CPUs | 8 (uniform) |
| Declared memory | 16G (uniform) |
| GPU required | none |
| Agent / verifier timeout | 3600 s |
| Build timeout | 1800 s |
| Problem size range | 1 – 6,291,456 |

Difficulty split: **medium** 154.

The problem-size spread matters operationally: the smallest tasks are cheap
smoke targets, the largest are what exhaust an under-provisioned Docker VM.

## Tasks

| # | Task | Difficulty | Problem size | Domain tags |
|---:|---|---|---:|---|
| 1 | `algotune-aes-gcm-encryption` | medium | 163,839 | optimization |
| 2 | `algotune-affine-transform-2d` | medium | 1,279 | optimization |
| 3 | `algotune-aircraft-wing-design` | medium | 10 | optimization |
| 4 | `algotune-articulation-points` | medium | 768 | optimization |
| 5 | `algotune-base64-encoding` | medium | 49,152 | optimization |
| 6 | `algotune-battery-scheduling` | medium | 5 | optimization |
| 7 | `algotune-btsp` | medium | 16 | optimization |
| 8 | `algotune-capacitated-facility-location` | medium | 4 | optimization |
| 9 | `algotune-chacha-encryption` | medium | 98,304 | optimization |
| 10 | `algotune-channel-capacity` | medium | 143 | optimization |
| 11 | `algotune-chebyshev-center` | medium | 192 | optimization |
| 12 | `algotune-cholesky-factorization` | medium | 2,048 | optimization |
| 13 | `algotune-clustering-outliers` | medium | 2,303 | optimization |
| 14 | `algotune-communicability` | medium | 56 | optimization |
| 15 | `algotune-convex-hull` | medium | 761,853 | optimization |
| 16 | `algotune-convolve-1d` | medium | 49,152 | optimization |
| 17 | `algotune-convolve2d-full-fill` | medium | 6 | optimization |
| 18 | `algotune-correlate-1d` | medium | 1,536 | optimization |
| 19 | `algotune-correlate2d-full-fill` | medium | 6 | optimization |
| 20 | `algotune-count-connected-components` | medium | 1,535 | optimization |
| 21 | `algotune-count-riemann-zeta-zeros` | medium | 16,384 | optimization |
| 22 | `algotune-cumulative-simpson-1d` | medium | 6,291,456 | optimization |
| 23 | `algotune-cumulative-simpson-multid` | medium | 448 | optimization |
| 24 | `algotune-cvar-projection` | medium | 9 | optimization |
| 25 | `algotune-cyclic-independent-set` | medium | 4 | optimization |
| 26 | `algotune-dct-type-i-scipy-fftpack` | medium | 2,175 | optimization |
| 27 | `algotune-delaunay` | medium | 14,336 | optimization |
| 28 | `algotune-dijkstra-from-indices` | medium | 5,119 | optimization |
| 29 | `algotune-discrete-log` | medium | 27 | optimization |
| 30 | `algotune-dst-type-ii-scipy-fftpack` | medium | 2,303 | optimization |
| 31 | `algotune-dynamic-assortment-planning` | medium | 28 | optimization |
| 32 | `algotune-earth-movers-distance` | medium | 1,279 | optimization |
| 33 | `algotune-edge-expansion` | medium | 4,223 | optimization |
| 34 | `algotune-eigenvalues-complex` | medium | 383 | optimization |
| 35 | `algotune-eigenvalues-real` | medium | 960 | optimization |
| 36 | `algotune-eigenvectors-complex` | medium | 383 | optimization |
| 37 | `algotune-eigenvectors-real` | medium | 896 | optimization |
| 38 | `algotune-elementwise-integration` | medium | 384 | optimization |
| 39 | `algotune-feedback-controller-design` | medium | 13 | optimization |
| 40 | `algotune-fft-cmplx-scipy-fftpack` | medium | 2,175 | optimization |
| 41 | `algotune-fft-convolution` | medium | 589,823 | optimization |
| 42 | `algotune-fft-real-scipy-fftpack` | medium | 3,072 | optimization |
| 43 | `algotune-firls` | medium | 864 | optimization |
| 44 | `algotune-generalized-eigenvalues-complex` | medium | 224 | optimization |
| 45 | `algotune-generalized-eigenvalues-real` | medium | 768 | optimization |
| 46 | `algotune-generalized-eigenvectors-complex` | medium | 224 | optimization |
| 47 | `algotune-generalized-eigenvectors-real` | medium | 639 | optimization |
| 48 | `algotune-graph-coloring-assign` | medium | 39 | optimization |
| 49 | `algotune-graph-global-efficiency` | medium | 448 | optimization |
| 50 | `algotune-graph-isomorphism` | medium | 120 | optimization |
| 51 | `algotune-graph-laplacian` | medium | 40,960 | optimization |
| 52 | `algotune-group-lasso` | medium | 143 | optimization |
| 53 | `algotune-gzip-compression` | medium | 639 | optimization |
| 54 | `algotune-integer-factorization` | medium | 186 | optimization |
| 55 | `algotune-job-shop-scheduling` | medium | 16 | optimization |
| 56 | `algotune-kalman-filter` | medium | 23 | optimization |
| 57 | `algotune-kcenters` | medium | 49 | optimization |
| 58 | `algotune-kd-tree` | medium | 159 | optimization |
| 59 | `algotune-kernel-density-estimation` | medium | 384 | optimization |
| 60 | `algotune-kmeans` | medium | 351 | optimization |
| 61 | `algotune-ks-test-2samp` | medium | 393,216 | optimization |
| 62 | `algotune-l0-pruning` | medium | 655,360 | optimization |
| 63 | `algotune-l1-pruning` | medium | 393,216 | optimization |
| 64 | `algotune-lasso` | medium | 383 | optimization |
| 65 | `algotune-least-squares` | medium | 98,304 | optimization |
| 66 | `algotune-linear-system-solver` | medium | 1,279 | optimization |
| 67 | `algotune-lp-box` | medium | 191 | optimization |
| 68 | `algotune-lp-centering` | medium | 191 | optimization |
| 69 | `algotune-lp-mdp` | medium | 9 | optimization |
| 70 | `algotune-lqr` | medium | 101 | optimization |
| 71 | `algotune-lti-simulation` | medium | 24,576 | optimization |
| 72 | `algotune-lu-factorization` | medium | 1,020 | optimization |
| 73 | `algotune-lyapunov-stability` | medium | 17 | optimization |
| 74 | `algotune-markowitz` | medium | 384 | optimization |
| 75 | `algotune-matrix-completion` | medium | 14 | optimization |
| 76 | `algotune-matrix-exponential` | medium | 639 | optimization |
| 77 | `algotune-matrix-exponential-sparse` | medium | 319 | optimization |
| 78 | `algotune-matrix-multiplication` | medium | 768 | optimization |
| 79 | `algotune-matrix-sqrt` | medium | 192 | optimization |
| 80 | `algotune-max-clique-cpsat` | medium | 14 | optimization |
| 81 | `algotune-max-common-subgraph` | medium | 5 | optimization |
| 82 | `algotune-max-flow-min-cost` | medium | 56 | optimization |
| 83 | `algotune-max-independent-set-cpsat` | medium | 14 | optimization |
| 84 | `algotune-max-weighted-independent-set` | medium | 71 | optimization |
| 85 | `algotune-min-dominating-set` | medium | 11 | optimization |
| 86 | `algotune-min-weight-assignment` | medium | 767 | optimization |
| 87 | `algotune-minimum-spanning-tree` | medium | 575 | optimization |
| 88 | `algotune-minimum-volume-ellipsoid` | medium | 27 | optimization |
| 89 | `algotune-multi-dim-knapsack` | medium | 55 | optimization |
| 90 | `algotune-nmf` | medium | 6 | optimization |
| 91 | `algotune-ode-brusselator` | medium | 192 | optimization |
| 92 | `algotune-ode-fitzhughnagumo` | medium | 20 | optimization |
| 93 | `algotune-ode-hires` | medium | 384 | optimization |
| 94 | `algotune-ode-hodgkinhuxley` | medium | 36 | optimization |
| 95 | `algotune-ode-lorenz96-nonchaotic` | medium | 6,144 | optimization |
| 96 | `algotune-ode-lotkavolterra` | medium | 160 | optimization |
| 97 | `algotune-ode-nbodyproblem` | medium | 6 | optimization |
| 98 | `algotune-ode-seirs` | medium | 1,536 | optimization |
| 99 | `algotune-ode-stiff-robertson` | medium | 786,432 | optimization |
| 100 | `algotune-ode-stiff-vanderpol` | medium | 1 | optimization |
| 101 | `algotune-odr` | medium | 24,576 | optimization |
| 102 | `algotune-optimal-advertising` | medium | 39 | optimization |
| 103 | `algotune-outer-product` | medium | 12,288 | optimization |
| 104 | `algotune-pagerank` | medium | 4,329 | optimization |
| 105 | `algotune-pca` | medium | 24 | optimization |
| 106 | `algotune-pde-burgers1d` | medium | 11 | optimization |
| 107 | `algotune-pde-heat1d` | medium | 8 | optimization |
| 108 | `algotune-polynomial-mixed` | medium | 383 | optimization |
| 109 | `algotune-polynomial-real` | medium | 351 | optimization |
| 110 | `algotune-power-control` | medium | 96 | optimization |
| 111 | `algotune-procrustes` | medium | 511 | optimization |
| 112 | `algotune-psd-cone-projection` | medium | 447 | optimization |
| 113 | `algotune-qp` | medium | 287 | optimization |
| 114 | `algotune-qr-factorization` | medium | 960 | optimization |
| 115 | `algotune-quantile-regression` | medium | 319 | optimization |
| 116 | `algotune-queens-with-obstacles` | medium | 11 | optimization |
| 117 | `algotune-queuing` | medium | 589,823 | optimization |
| 118 | `algotune-qz-factorization` | medium | 240 | optimization |
| 119 | `algotune-randomized-svd` | medium | 480 | optimization |
| 120 | `algotune-rbf-interpolation` | medium | 10 | optimization |
| 121 | `algotune-rectanglepacking` | medium | 9 | optimization |
| 122 | `algotune-robust-kalman-filter` | medium | 12 | optimization |
| 123 | `algotune-robust-linear-program` | medium | 12 | optimization |
| 124 | `algotune-rocket-landing-optimization` | medium | 96 | optimization |
| 125 | `algotune-rotate-2d` | medium | 1,151 | optimization |
| 126 | `algotune-set-cover` | medium | 53 | optimization |
| 127 | `algotune-set-cover-conflicts` | medium | 55 | optimization |
| 128 | `algotune-sha256-hashing` | medium | 163,839 | optimization |
| 129 | `algotune-shift-2d` | medium | 1,279 | optimization |
| 130 | `algotune-shortest-path-dijkstra` | medium | 319 | optimization |
| 131 | `algotune-sinkhorn` | medium | 1,535 | optimization |
| 132 | `algotune-sparse-eigenvectors-complex` | medium | 1,279 | optimization |
| 133 | `algotune-sparse-lowest-eigenvalues-posdef` | medium | 1,279 | optimization |
| 134 | `algotune-sparse-lowest-eigenvectors-posdef` | medium | 1,279 | optimization |
| 135 | `algotune-sparse-pca` | medium | 639 | optimization |
| 136 | `algotune-spectral-clustering` | medium | 25 | optimization |
| 137 | `algotune-stable-matching` | medium | 1,151 | optimization |
| 138 | `algotune-svd` | medium | 448 | optimization |
| 139 | `algotune-svm` | medium | 575 | optimization |
| 140 | `algotune-sylvester-solver` | medium | 96 | optimization |
| 141 | `algotune-tensor-completion-3d` | medium | 5 | optimization |
| 142 | `algotune-toeplitz-solver` | medium | 8,703 | optimization |
| 143 | `algotune-tsp` | medium | 35 | optimization |
| 144 | `algotune-two-eigenvalues-around-0` | medium | 1,151 | optimization |
| 145 | `algotune-unit-simplex-projection` | medium | 786,432 | optimization |
| 146 | `algotune-upfirdn1d` | medium | 3,072 | optimization |
| 147 | `algotune-vector-quantization` | medium | 143 | optimization |
| 148 | `algotune-vectorized-newton` | medium | 655,360 | optimization |
| 149 | `algotune-vehicle-routing` | medium | 12 | optimization |
| 150 | `algotune-vertex-cover` | medium | 15 | optimization |
| 151 | `algotune-voronoi-diagram` | medium | 12,288 | optimization |
| 152 | `algotune-wasserstein-dist` | medium | 81,920 | optimization |
| 153 | `algotune-water-filling` | medium | 3,072 | optimization |
| 154 | `algotune-zoom-2d` | medium | 960 | optimization |

## Smallest tasks (cheapest to smoke-test)

| Task | Problem size |
|---|---:|
| `algotune-ode-stiff-vanderpol` | 1 |
| `algotune-capacitated-facility-location` | 4 |
| `algotune-cyclic-independent-set` | 4 |
| `algotune-battery-scheduling` | 5 |
| `algotune-max-common-subgraph` | 5 |
| `algotune-tensor-completion-3d` | 5 |
| `algotune-convolve2d-full-fill` | 6 |
| `algotune-correlate2d-full-fill` | 6 |
| `algotune-nmf` | 6 |
| `algotune-ode-nbodyproblem` | 6 |
| `algotune-pde-heat1d` | 8 |
| `algotune-cvar-projection` | 9 |

## Not committed

`results/` is gitignored, so none of these 154 task packages are tracked by
git — `git ls-files | grep algotune` returns nothing. They exist only on the
machine that downloaded them. Promoting AlgoTune to a real task source means
vendoring the selected subset under a tracked path and recording the
`harbor-datasets` commit as provenance.

