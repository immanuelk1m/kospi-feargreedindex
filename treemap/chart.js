function loadItems() {
  return fetch("https://www.kospi-fear-greed-index.co.kr/treemap/output.json") // change
    .then((response) => response.json())
    .then((json) => json);
}

loadItems().then((items) => {
  
  var data = items.series;
  var date = items.categories;
  
  var options = {
    series: data ,
    
    chart: {
    height: 350,
    type: 'line',
    zoom: {
      enabled: false
    },
  },
  dataLabels: {
    enabled: false
  },
  stroke: {
    width: [5, 7, 5],
    curve: 'straight',
    dashArray: [0, 8, 5]
  },
  title: {
    text: 'Page Statistics',
    align: 'middle'
  },
  legend: {
    tooltipHoverFormatter: function(val, opts) {
      return val + ' - ' + opts.w.globals.series[opts.seriesIndex][opts.dataPointIndex] + ''
    }
  },
  markers: {
    size: 0,
    hover: {
      sizeOffset: 6
    }
  },
  xaxis: {
    categories: date,
    tickAmount: 7
  },
  yaxis : {
    opposite : true,
    forceNiceScale: false,
    min: -50,
    max: 50,
    labels: {
      formatter: (value) => value.toFixed(0)+'%',
  }
  },
    

  tooltip: {
    y: [
      {
        title: {
          formatter: function (val) {
            return val + " (mins)"
          }
        }
      },
      {
        title: {
          formatter: function (val) {
            return val + " per session"
          }
        }
      },
      {
        title: {
          formatter: function (val) {
            return val;
          }
        }
      }
    ]
  },
  grid: {
    borderColor: '#f1f1f1',
  }
  };

  var chart = new ApexCharts(document.querySelector("#chart"), options);
  chart.render();



});
