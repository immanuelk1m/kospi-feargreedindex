function sort_object(obj) 
{
    items = Object.keys(obj).map(function(key) {
        return [key, obj[key]];
    });
    items.sort(function(first, second) {
        return second[1] - first[1];
    });
    sorted_obj={}
    $.each(items, function(k, v) {
        use_key = v[0]
        use_value = v[1]
        sorted_obj[use_key] = use_value
    })
    return(sorted_obj)
}    
function loadItems() {
return fetch("https://www.kospi-fear-greed-index.co.kr/treemap/output.json") 
.then((response) => response.json())
.then((json) => json);
}

loadItems().then((items) => {
    var data = items.series;
    var date = items.categories;
    var len = data[0].data.length-1;

    var ratio_dict = {};

    const rowCnt = 21;

    for (let i = 0; i < rowCnt; i++)
    {
        ratio_dict[data[i].name] = data[i].data[len]
    }
    obj = sort_object(ratio_dict);

    var html = "<table> <thead>";
    
    html += "<tr>";
    html += "<td>산업 섹터 💡</td>";
    html += "<td>수익률 성과 📈</td>";
    html += "</tr> <thead>";

        for (let i = 0; i < rowCnt; i++)
    {
        html += "<tr>";
        html += "<td>" + Object.keys(obj)[i] + "</td>";
        html += "<td>" + String(Object.values(obj)[i]) + "% </td>";
        html += "</tr>";
        
    }
    html += "</table>";
    
    document.getElementById("sector_table").innerHTML = html;
    
})
