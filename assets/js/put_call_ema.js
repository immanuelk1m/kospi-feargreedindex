function loadItems() {
  return fetch("assets/js/json/p_c_ema.json") // change
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
    
    var speedCanvas = document.getElementById("putcall_chart"); // change


    var dataFirst = {
        label: "Put/Call Ratio", // change
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
