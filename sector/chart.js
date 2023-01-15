function loadItems() {
  return fetch("https://www.kospi-fear-greed-index.co.kr/sector/output.json") // change
    .then((response) => response.json())
    .then((json) => json);
}

loadItems().then((items) => {
  
  var data = items.series;
  var date = items.categories;
  
  var options = {
    series: data ,
    
    chart: {
    height: 600,
    type: 'line',
    zoom: {
      enabled: true
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
    text: '코스피 산업 분야별 성과',
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
    type: 'datetime',
    labels: {
      format: 'MM yyyy'
    },
    categories: date,
    tickAmount: 5
  },
  yaxis : {
    opposite : true,
    forceNiceScale: true,
    min: -40,
    max: 40,
    tickAmount: 5,
    labels: {
      formatter: (value) => value.toFixed(0)+'%',
  }
  },
    

  tooltip: {
    shared: true,
    intersect: false,
    y: 
      {
        title: {
          formatter: function (val) {
            return val + "%";
          }
        }
      },
    
  },
  grid: {
    borderColor: '#f1f1f1',
  }
  };

  var chart = new ApexCharts(document.querySelector("#chart"), options);
  chart.render();



});
