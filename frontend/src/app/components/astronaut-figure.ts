import { Component } from '@angular/core';

/** Grayscale astronaut drawn in SVG, with a blurred "motion" copy behind it. */
@Component({
  selector: 'app-astronaut-figure',
  host: { style: 'display: contents' },
  template: `
    <svg class="astronaut" viewBox="0 0 320 520" role="img" aria-label="Astronaut body map, SI-generated illustration">
      <defs>
        <linearGradient id="suit" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stop-color="#fbfbfa" />
          <stop offset="0.55" stop-color="#d3d3d1" />
          <stop offset="1" stop-color="#8e8e8c" />
        </linearGradient>
        <linearGradient id="suit-dark" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stop-color="#bebebc" />
          <stop offset="1" stop-color="#6b6b69" />
        </linearGradient>
        <radialGradient id="visor" cx="0.35" cy="0.3" r="0.9">
          <stop offset="0" stop-color="#4c4c4c" />
          <stop offset="0.6" stop-color="#141414" />
          <stop offset="1" stop-color="#000" />
        </radialGradient>
        <radialGradient id="halo" cx="0.5" cy="0.45" r="0.5">
          <stop offset="0" stop-color="#fff" stop-opacity="0.95" />
          <stop offset="1" stop-color="#fff" stop-opacity="0" />
        </radialGradient>
        <filter id="ghost-blur" x="-30%" y="-20%" width="160%" height="140%">
          <feGaussianBlur stdDeviation="8" />
        </filter>
        <filter id="soft-shadow" x="-20%" y="-10%" width="140%" height="130%">
          <feDropShadow dx="0" dy="16" stdDeviation="14" flood-color="#000" flood-opacity="0.2" />
        </filter>
      </defs>

      <ellipse cx="160" cy="250" rx="160" ry="240" fill="url(#halo)" />
      <use href="#astro-body" transform="translate(-38 8)" filter="url(#ghost-blur)" opacity="0.5" />

      <g id="astro-body" filter="url(#soft-shadow)">
        <rect x="96" y="128" width="128" height="168" rx="28" fill="url(#suit-dark)" />

        <path d="M138 296 C134 350 132 400 130 452" stroke="#cbcbc9" stroke-width="44" stroke-linecap="round" fill="none" />
        <path d="M182 296 C186 350 188 400 190 452" stroke="#b9b9b7" stroke-width="44" stroke-linecap="round" fill="none" />
        <path d="M132 304 C129 350 128 398 126 444" stroke="#efefee" stroke-width="12" stroke-linecap="round" fill="none" opacity="0.7" />
        <ellipse cx="133" cy="378" rx="22" ry="15" fill="#acacaa" />
        <ellipse cx="187" cy="378" rx="22" ry="15" fill="#a1a19f" />
        <rect x="100" y="446" width="60" height="34" rx="14" fill="#5f5f5d" />
        <rect x="160" y="446" width="60" height="34" rx="14" fill="#535351" />

        <path d="M112 172 C86 204 76 244 72 292" stroke="#d0d0ce" stroke-width="38" stroke-linecap="round" fill="none" />
        <path d="M208 172 C234 204 244 244 248 292" stroke="#b8b8b6" stroke-width="38" stroke-linecap="round" fill="none" />
        <path d="M104 184 C86 212 78 246 75 284" stroke="#f1f1f0" stroke-width="9" stroke-linecap="round" fill="none" opacity="0.75" />
        <circle cx="72" cy="302" r="19" fill="#7a7a78" />
        <circle cx="248" cy="302" r="19" fill="#6c6c6a" />

        <path
          d="M108 158 C140 146 180 146 212 158 C220 200 224 250 222 292 C190 306 130 306 98 292 C96 250 100 200 108 158 Z"
          fill="url(#suit)"
        />
        <circle cx="112" cy="170" r="24" fill="#e0e0de" />
        <circle cx="208" cy="170" r="24" fill="#c4c4c2" />
        <rect x="100" y="282" width="120" height="20" rx="10" fill="#9c9c9a" />

        <rect x="132" y="198" width="56" height="38" rx="10" fill="#f5f5f4" stroke="#a9a9a7" stroke-width="2" />
        <circle cx="146" cy="217" r="4" fill="#8a8a88" />
        <circle cx="160" cy="217" r="4" fill="#8a8a88" />
        <circle cx="174" cy="217" r="4" fill="#8a8a88" />

        <rect x="116" y="138" width="88" height="20" rx="10" fill="#b3b3b1" />
        <circle cx="160" cy="86" r="60" fill="url(#suit)" />
        <rect x="116" y="56" width="88" height="68" rx="30" fill="url(#visor)" />
        <path d="M128 74 C136 64 150 60 162 60" stroke="#fff" stroke-opacity="0.55" stroke-width="5" stroke-linecap="round" fill="none" />
        <circle cx="190" cy="106" r="3" fill="#fff" opacity="0.35" />
      </g>
      <g data-si-watermark="true" pointer-events="none">
        <rect x="63" y="493" width="194" height="24" rx="5" fill="#ffffff" fill-opacity="0.96" />
        <text x="160" y="509" text-anchor="middle" fill="#444444" font-family="Arial, sans-serif" font-size="12.5">SI-generated illustration</text>
      </g>
    </svg>
  `,
})
export class AstronautFigure {}
