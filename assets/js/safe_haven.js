function loadItems() {
  return fetch("https://www.kospi-fear-greed-index.co.kr/assets/js/json/safe_spread.json") // change
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

    
    
    /////////////////////////////////////////////////////////
    
    var speedCanvas = document.getElementById("safe_demand_chart"); // change


    var dataFirst = {
        label: "Safe Demand", // change
        data: ydata,
        lineTension: 0,
        fill: false,
        borderColor: 'rgba(77,20,140)',
        pointRadius: 2,
    };

    

    var speedData = {
        labels: labels,
        datasets: [dataFirst]
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
