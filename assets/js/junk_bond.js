function loadItems() {
  return fetch("assets/js/json/junk_spread.json") // change
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
    
    var speedCanvas = document.getElementById("junk_bond_chart"); // change


    var dataFirst = {
        label: "Junk Bond Demand", // change
        data: ydata,
        lineTension: 0,
        fill: false,
        borderColor: 'rgba(77,20,140)'
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
                    tooltipFormat:'MM/dd/yyyy',
                    
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
