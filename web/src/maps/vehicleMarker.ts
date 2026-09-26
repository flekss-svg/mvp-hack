// Static SVG artwork stays sharp at every map scale, without external image requests.
export const vehicleMarkerTemplate = `
<button type="button" class="$[properties.className]" aria-label="$[properties.label]" data-vehicle-id="$[properties.vehicleKey]">
  <span class="vehicle-risk" aria-hidden="true"><span>!</span></span>
  <span class="vehicle-model-unknown" aria-hidden="true">ТС</span>
  <svg class="vehicle-model vehicle-model-bus" viewBox="0 0 40 40" aria-hidden="true" focusable="false">
    <ellipse cx="20" cy="36" rx="15" ry="3" fill="#20374b" opacity=".18"/>
    <g stroke="#17384f" stroke-width="1.2" stroke-linejoin="round">
      <rect x="8" y="29" width="5" height="8" rx="2" fill="#253746"/>
      <rect x="27" y="29" width="5" height="8" rx="2" fill="#253746"/>
      <path d="M8 5Q20 1 32 5L34 30Q34 34 30 34H10Q6 34 6 30Z" fill="#338bc2"/>
      <path d="M10 9H30L31 22H9Z" fill="#cceefa"/>
      <path d="M20 9V22M10 24H30" fill="none"/>
      <path d="M11 11H17L11 19Z" fill="#fff" stroke="none" opacity=".75"/>
      <rect x="13" y="5" width="14" height="3" rx="1" fill="#17384f" stroke="none"/>
      <rect x="8" y="27" width="6" height="3" rx="1" fill="#fff4c5" stroke="none"/>
      <rect x="26" y="27" width="6" height="3" rx="1" fill="#fff4c5" stroke="none"/>
      <path d="M17 29H23M8 32H32" fill="none"/>
      <path d="M5 12H3V19H6M35 12H37V19H34" fill="#338bc2"/>
    </g>
  </svg>
  <svg class="vehicle-model vehicle-model-tram" viewBox="0 0 40 40" aria-hidden="true" focusable="false">
    <ellipse cx="20" cy="36" rx="15" ry="3" fill="#20374b" opacity=".18"/>
    <g stroke="#4e3043" stroke-width="1.2" stroke-linejoin="round">
      <path d="M10 39L15 31M30 39L25 31" fill="none" stroke="#697f8c"/>
      <path d="M20 9L13 5L20 1L27 5Z" fill="none"/>
      <path d="M13 1H27" fill="none"/>
      <path d="M12 8H28Q33 8 33 14V29Q33 35 27 35H13Q7 35 7 29V14Q7 8 12 8Z" fill="#c65b6d"/>
      <path d="M11 14H29V25H11Z" fill="#d8eef5"/>
      <path d="M20 14V25" fill="none"/>
      <path d="M12 15H17L12 22Z" fill="#fff" stroke="none" opacity=".8"/>
      <rect x="14" y="10" width="12" height="3" rx="1" fill="#4e3043" stroke="none"/>
      <path d="M8 27H32" stroke="#fff0df" stroke-width="3"/>
      <circle cx="12" cy="30" r="2" fill="#fff4c5" stroke="none"/>
      <circle cx="28" cy="30" r="2" fill="#fff4c5" stroke="none"/>
      <path d="M17 33H23M20 35V38" fill="none" stroke-width="2"/>
    </g>
  </svg>
  <span class="vehicle-route" aria-hidden="true">$[properties.route]</span>
</button>`
