/**
 * Analytics charts (Chart.js - MIT licensed, served locally, no CDN account).
 * Datasets are emitted into the page as JSON via Django's `json_script`.
 */
(function () {
  "use strict";

  if (typeof Chart === "undefined") {
    return;
  }

  var PALETTE = [
    "#7b1030",
    "#1f7a4d",
    "#b8860b",
    "#2b6cb0",
    "#6b46c1",
    "#c05621",
    "#4a5568"
  ];

  function read(id) {
    var node = document.getElementById(id);
    if (!node) {
      return null;
    }
    try {
      return JSON.parse(node.textContent);
    } catch (error) {
      return null;
    }
  }

  function build(canvasId, type, labels, values, label) {
    var canvas = document.getElementById(canvasId);
    if (!canvas || !labels || !labels.length) {
      return;
    }
    var isLine = type === "line";
    new Chart(canvas.getContext("2d"), {
      type: type,
      data: {
        labels: labels,
        datasets: [
          {
            label: label,
            data: values,
            backgroundColor: isLine
              ? "rgba(123, 16, 48, 0.15)"
              : labels.map(function (_item, index) {
                  return PALETTE[index % PALETTE.length];
                }),
            borderColor: isLine ? "#7b1030" : "#ffffff",
            borderWidth: isLine ? 2 : 1,
            fill: isLine,
            tension: 0.3
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: type === "doughnut", position: "bottom" },
          tooltip: { intersect: false, mode: "index" }
        },
        scales: type === "doughnut"
          ? {}
          : {
              y: { beginAtZero: true, ticks: { precision: 0 } },
              x: { grid: { display: false } }
            }
      }
    });
  }

  function pluck(rows, key, fallback) {
    return rows.map(function (row) {
      return row[key] === null || row[key] === undefined ? fallback : row[key];
    });
  }

  var byDepartment = read("chart-department-data") || [];
  build(
    "chart-department",
    "bar",
    pluck(byDepartment, "department__name", "Unassigned"),
    pluck(byDepartment, "total", 0),
    "Complaints"
  );

  var byStatus = read("chart-status-data") || [];
  build(
    "chart-status",
    "doughnut",
    pluck(byStatus, "status", "-"),
    pluck(byStatus, "total", 0),
    "Complaints"
  );

  var byCategory = read("chart-category-data") || [];
  build(
    "chart-category",
    "bar",
    pluck(byCategory, "category", "-"),
    pluck(byCategory, "total", 0),
    "Complaints"
  );

  var monthly = read("chart-monthly-data") || [];
  build(
    "chart-monthly",
    "line",
    pluck(monthly, "label", "-"),
    pluck(monthly, "total", 0),
    "Complaints per month"
  );
})();
