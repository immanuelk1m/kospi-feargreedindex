function loadItems() {
  return fetch("assets/js/json/index.json") // change
    .then((response) => response.json())
    .then((json) => json);
}

loadItems().then((items) => {
  
    var labels = items.data.map(function(e) {
        return e.x;
    });
    
    var ydata = items.data.map(function(e) {
        return e.y;
    });
    var y2data = items.data.map(function(e) {   // change if y2 exsis
        return e.z;
    });
    
    
    /////////////////////////////////////////////////////////
    
    var speedCanvas = document.getElementById("index_line"); // change


    var dataFirst = {
        yAxisID: 'A',
        label: "Kospi", // change
        data: ydata,
        lineTension: 0,
        fill: false,
        borderColor: 'rgba(77,20,140)'
        pointRadius: 0,
    };

    var dataSecond = {
        yAxisID: 'B',
        label: "Fear & Greed Index",  // change
        data: y2data,
        lineTension: 0,
        fill: false,
        borderColor: 'rgba(255,102,0)',
        pointRadius: 0,
    };

    var speedData = {
        labels: labels,
        datasets: [dataFirst, dataSecond]
    };

    var chartOptions = {
        responsive: false,
        legend: {
            display: true,
            position: 'top',
            labels: {
                boxWidth: 80,
                fontColor: 'black'
            }
        },
        scales: {
            x: {
                type: 'time',
                time: {
                    unit: 'month',
                    tooltipFormat:'MM/dd/yyyy',
                    
                },
              ticks: {
                autoSkip: true,
                maxTicksLimit: 6
              }
            },
            A: {
                type: 'linear',
                display: true,
                position: 'left',
            },
            B:
            {
                type: 'linear',
                display: true,
                position: 'right',

                // grid line settings
                grid: {
                    drawOnChartArea: false, // only want the grid lines for one axis to show up
                },
            }
        },
  
    };

    var lineChart = new Chart(speedCanvas, {
        type: 'line',
        data: speedData,
        options: chartOptions
    });

    
    
    
});
