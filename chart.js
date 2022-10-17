am4core.ready(function() {

// Themes begin
am4core.useTheme(am4themes_animated);
// Themes end
am4core.addLicense("ch-custom-attribution");
    
var chartMin = 0;
var chartMax = 100;
    
var data = {
  score: 50,
  gradingData: [
    {
      title: "😱",
      color: "#ee1f25",
      lowScore: 0,
      highScore: 20
    },
    {
      title: "😨",
      color: "#fdae19",
      lowScore: 20,
      highScore: 40
    },
    {
      title: "😐",
      color: "#f3eb0c",
      lowScore: 40,
      highScore: 60
    },
    {
      title: "😀",
      color: "#b0d136",
      lowScore: 60,
      highScore: 80
    },
    {
      title: "🤑",
      color: "#0f9747",
      lowScore: 80,
      highScore: 100
    }
  ]
};

/**
Grading Lookup
 */
function lookUpGrade(lookupScore, grades) {
  // Only change code below this line
  for (var i = 0; i < grades.length; i++) {
    if (
      grades[i].lowScore < lookupScore &&
      grades[i].highScore >= lookupScore
    ) {
      return grades[i];
    }
  }
  return null;
}

// create chart
var chart = am4core.create("chartdiv", am4charts.GaugeChart);
if(chart.logo){
    chart.logo.disabled = true;
}
chart.hiddenState.properties.opacity = 0;
chart.fontSize = 7; // Fear font Size
chart.innerRadius = am4core.percent(70);
chart.resizable = true;

/**
 * Normal axis
 */

var axis = chart.xAxes.push(new am4charts.ValueAxis());
axis.min = chartMin;
axis.max = chartMax;
axis.strictMinMax = true;
axis.renderer.radius = am4core.percent(60);
axis.renderer.inside = true;
axis.renderer.line.strokeOpacity = 0.2;
axis.renderer.ticks.template.disabled = false;
axis.renderer.ticks.template.strokeOpacity = 1;
axis.renderer.ticks.template.strokeWidth = 0.5;
axis.renderer.ticks.template.length = 10;
axis.renderer.grid.template.disabled = true;
axis.renderer.labels.template.radius = am4core.percent(20);
axis.renderer.labels.template.fontSize = "1.6em";

/**
 * Axis for ranges
 */

var axis2 = chart.xAxes.push(new am4charts.ValueAxis());
axis2.min = chartMin;
axis2.max = chartMax;
axis2.strictMinMax = true;
axis2.renderer.labels.template.disabled = true;
axis2.renderer.ticks.template.disabled = true;
axis2.renderer.grid.template.disabled = false;
axis2.renderer.grid.template.opacity = 0.5;
axis2.renderer.labels.template.bent = true;
axis2.renderer.labels.template.fill = am4core.color("#000");
axis2.renderer.labels.template.fontWeight = "bold";
axis2.renderer.labels.template.fillOpacity = 1;



/**
Ranges
*/

for (let grading of data.gradingData) {
  var range = axis2.axisRanges.create();
  range.axisFill.fill = am4core.color(grading.color);
  range.axisFill.fillOpacity = 0.8;
  range.axisFill.zIndex = -1;
  range.value = grading.lowScore > chartMin ? grading.lowScore : chartMin;
  range.endValue = grading.highScore < chartMax ? grading.highScore : chartMax;
  range.grid.strokeOpacity = 0;
  range.stroke = am4core.color(grading.color).lighten(-0.1);
  range.label.inside = true;
  range.label.text = grading.title.toUpperCase();
  range.label.inside = true;
  range.label.location = 0.5;
  range.label.inside = true;
  range.label.radius = am4core.percent(10);
  range.label.paddingBottom = -5; // ~half font size
  range.label.fontSize = "3.2em";
}

var matchingGrade = lookUpGrade(data.score, data.gradingData);

/**
 * Label 1
 */

var label = chart.radarContainer.createChild(am4core.Label);
label.isMeasured = false;
label.fontSize = "4em";
label.x = am4core.percent(50);
label.paddingBottom = 25;
label.horizontalCenter = "middle";
label.verticalCenter = "bottom";
//label.dataItem = data;
label.text = data.score.toFixed(1);
//label.text = "{score}";
label.fill = am4core.color(matchingGrade.color);

/**
 * Label 2
 */

var label2 = chart.radarContainer.createChild(am4core.Label);
label2.isMeasured = false;
label2.fontSize = "3em";
label2.horizontalCenter = "middle";
label2.verticalCenter = "bottom";
label2.text = matchingGrade.title.toUpperCase();
label2.fill = am4core.color(matchingGrade.color);


/**
 * Hand
 */

var hand = chart.hands.push(new am4charts.ClockHand());
hand.axis = axis2;
hand.innerRadius = am4core.percent(60);
hand.startWidth = 5;
hand.pin.disabled = true;
hand.value = data.score;
hand.fill = am4core.color("#444");
hand.stroke = am4core.color("#000");

hand.events.on("positionchanged", function(){
  label.text = axis2.positionToValue(hand.currentPosition).toFixed(1);
  var value2 = axis.positionToValue(hand.currentPosition);
  var matchingGrade = lookUpGrade(axis.positionToValue(hand.currentPosition), data.gradingData);
  label2.text = matchingGrade.title.toUpperCase();
  label2.fill = am4core.color(matchingGrade.color);
  label2.stroke = am4core.color(matchingGrade.color);  
  label.fill = am4core.color(matchingGrade.color);
})

    
    
var current_value;
    
fetch("value.json")
  .then(response => response.json())
  .then(json => current_value = json.current);

    
setInterval(function() {
    var value = 0 + current_value/10 * (10 - 0);
    hand.showValue(value, 1000, am4core.ease.cubicOut);
}, 2000);

    
}); // end am4core.ready()
    
