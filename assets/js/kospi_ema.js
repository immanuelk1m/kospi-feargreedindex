function loadItems() {
  return fetch("https://kospi-fear-greed-index.co.kr/assets/js/json/kospi.json")
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
    var y2data = items.data.map(function(e) {
        return e.z;
    });
    
    
    /////////////////////////////////////////////////////////
    
    var speedCanvas = document.getElementById("kospi_momentum");


    var dataFirst = {
        label: "Kospi",
        data: ydata,
        lineTension: 0,
        fill: false,
        borderColor: 'rgba(77,20,140)',
        pointRadius: 0,
    };

    var dataSecond = {
        label: "Kospi 125EMA",
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
                    tooltipFormat:'MM/DD/yyyy',
                    
                },
              ticks: {
                autoSkip: true,
                maxTicksLimit: 6
              }
            }
        },
  
    };

    var lineChart = new Chart(speedCanvas, {
        type: 'line',
        data: speedData,
        options: chartOptions
    });

    
    
    
});
