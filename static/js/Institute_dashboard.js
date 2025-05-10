// Dynamic Calendar (the right panel uses this)
let currentMonth;
let currentYear;
const todayDate = new Date();
document.addEventListener("DOMContentLoaded", function () {
  const today = new Date();
  currentMonth = today.getMonth();
  currentYear = today.getFullYear();
  updateCalendar(currentMonth, currentYear);
  document.getElementById("prevMonth").addEventListener("click", () => {
    currentMonth--;
    if (currentMonth < 0) {
      currentMonth = 11;
      currentYear--;
    }
    updateCalendar(currentMonth, currentYear);
  });
  document.getElementById("nextMonth").addEventListener("click", () => {
    currentMonth++;
    if (currentMonth > 11) {
      currentMonth = 0;
      currentYear++;
    }
    updateCalendar(currentMonth, currentYear);
  });
});
function updateCalendar(month, year) {
  const monthNames = ["January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"];
  document.getElementById("monthYear").textContent = monthNames[month] + " " + year;
  document.getElementById("calendarContainer").innerHTML = generateCalendar(month, year);
}
function generateCalendar(month, year) {
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const firstDay   = new Date(year, month, 1).getDay();
  const dayNames   = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
  let table = "<table><thead><tr>";
  dayNames.forEach(d => table += `<th>${d}</th>`);
  table += `</tr></thead><tbody>`;

  let date = 1;
  for (let row = 0; row < 6; row++) {
    table += "<tr>";
    for (let col = 0; col < 7; col++) {
      if (row === 0 && col < firstDay) {
        table += "<td></td>";
      } else if (date > daysInMonth) {
        table += "<td></td>";
      } else {
        // check if this cell is today
        const isToday = 
          date === todayDate.getDate() &&
          month === todayDate.getMonth() &&
          year  === todayDate.getFullYear();

        table += `<td${isToday ? ' class="today"' : ''}>${date}</td>`;
        date++;
      }
    }
    table += "</tr>";
    if (date > daysInMonth) break;
  }
  table += "</tbody></table>";
  return table;
}
