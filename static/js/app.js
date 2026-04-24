document.addEventListener("DOMContentLoaded", () => {
  const chartCanvas = document.getElementById("subscriptionsChart");

  if (chartCanvas && typeof Chart !== "undefined") {
    const rawData = chartCanvas.getAttribute("data-chart");
    let chartData = [];

    try {
      chartData = JSON.parse(rawData);
    } catch (error) {
      console.error("Error leyendo datos del gráfico:", error);
    }

    if (chartData.length > 0) {
      new Chart(chartCanvas, {
        type: "bar",
        data: {
          labels: chartData.map(item => item.name),
          datasets: [{
            label: "Coste mensual estimado (€)",
            data: chartData.map(item => item.value),
            backgroundColor: chartData.map(item => item.color),
            borderRadius: 10,
            borderSkipped: false
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: false
            },
            tooltip: {
              callbacks: {
                label: function(context) {
                  return context.raw + " € / mes";
                }
              }
            }
          },
          scales: {
            x: {
              ticks: {
                color: getComputedStyle(document.body).getPropertyValue("--muted")
              },
              grid: {
                display: false
              }
            },
            y: {
              beginAtZero: true,
              ticks: {
                color: getComputedStyle(document.body).getPropertyValue("--muted")
              },
              grid: {
                color: "rgba(255,255,255,0.08)"
              }
            }
          }
        }
      });
    }
  }

  const themeToggle = document.getElementById("themeToggle");
  const savedTheme = localStorage.getItem("subsy_theme");

  if (savedTheme === "light") {
    document.body.classList.add("light-mode");
    if (themeToggle) {
      themeToggle.textContent = "☀️";
    }
  }

  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      document.body.classList.toggle("light-mode");

      const isLight = document.body.classList.contains("light-mode");
      localStorage.setItem("subsy_theme", isLight ? "light" : "dark");
      themeToggle.textContent = isLight ? "☀️" : "🌙";
    });
  }

  const notificationBell = document.getElementById("notificationBell");
  const notificationDropdown = document.getElementById("notificationDropdown");

  if (notificationBell && notificationDropdown) {
    notificationBell.addEventListener("click", (e) => {
      e.stopPropagation();
      notificationDropdown.classList.toggle("show");
    });

    notificationDropdown.addEventListener("click", (e) => {
      e.stopPropagation();
    });

    document.addEventListener("click", () => {
      notificationDropdown.classList.remove("show");
    });
  }
});