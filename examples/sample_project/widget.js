// Esempio didattico con violazioni green lato frontend.

function buildMatrix(rows, cols) {
  // GC001: ciclo annidato
  const grid = [];
  for (let i = 0; i < rows.length; i++) {
    for (let j = 0; j < cols.length; j++) {
      grid.push(rows[i] * cols[j]);
    }
  }
  return grid;
}

// GC063: setInterval ad alta frequenza (<100ms)
setInterval(() => refresh(), 16);

function refresh() {
  console.log("refreshing widget"); // GC040: console.log di debug
}
